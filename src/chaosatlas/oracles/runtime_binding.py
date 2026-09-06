"""Bind transaction HTTP traffic and release audits to an IsolationManager lease."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
import re
import subprocess
import threading
from typing import Any

from chaosatlas.isolation.manager import IsolationManager
from chaosatlas.isolation.contracts import canonical_hash, validate_lease, verify_hash
from chaosatlas.isolation.providers import KubernetesIsolationProvider


class LeaseRuntime:
    # A verified target is not proof that a business transaction ran successfully.

    def __init__(self, manager: IsolationManager, lease_id: str, *, service: str, port: int,
                 principal_id: str | None = None, project_revision: str):
        if not isinstance(manager, IsolationManager):
            raise ValueError('public IsolationManager required')
        if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,62}', service) or type(port) is not int or not 1 <= port <= 65535:
            raise ValueError('invalid service binding')
        self.manager = manager
        self.lease_id = lease_id
        self.service = service
        self.port = port
        self.principal_id = principal_id
        self.project_revision = project_revision
        self._binding: dict[str, str] | None = None
        self._tunnel: subprocess.Popen | None = None

    def bind_principal(self, references: list[dict[str, Any]]) -> dict[str, Any]:
        """Derive the runtime principal from Secret metadata owned by this lease.

        The caller cannot choose a v3 principal ID.  Values are deliberately not
        decoded here; SecretHeaders performs the later exact key/value read.
        """
        if self._binding is not None or self._tunnel is not None:
            raise ValueError('principal must be bound before the runtime tunnel opens')
        lease = self._lease()
        if lease['plan'].get('mode') == 'adopted-test-replica':
            raise ValueError('lease-owned principal requires a disposable lease')
        if not isinstance(references, list) or not references:
            raise ValueError('lease-owned credential references required')
        namespace = str(lease.get('target_name') or '')
        provider = self.manager.providers.get(lease['provider'])
        principals: set[str] = set()
        bindings: list[dict[str, str]] = []
        for reference in references:
            if (
                not isinstance(reference, dict)
                or reference.get('source') != 'lease_owned_secret_ref'
                or not isinstance(reference.get('secret_name'), str)
                or not isinstance(reference.get('principal_role'), str)
            ):
                raise ValueError('runtime principal requires logical lease-owned credentials')
            name = reference['secret_name']
            registered = [item for item in lease.get('resources') or []
                          if item.get('kind') == 'Secret'
                          and item.get('namespace') == namespace
                          and item.get('name') == name]
            value, error = provider._json(
                lease['plan'], ['-n', namespace, 'get', 'secret', name], lease=lease,
            )
            metadata = (value or {}).get('metadata') or {}
            labels = metadata.get('labels') or {}
            annotations = metadata.get('annotations') or {}
            principal = annotations.get('chaosatlas.dev/principal-id')
            if (
                error
                or len(registered) != 1
                or not registered[0].get('actual_uid')
                or metadata.get('uid') != registered[0]['actual_uid']
                or metadata.get('namespace') != namespace
                or metadata.get('name') != name
                or any(labels.get(key) != str(expected) for key, expected in (lease.get('owner_labels') or {}).items())
                or annotations.get('chaosatlas.dev/principal-role') != reference['principal_role']
                or not isinstance(principal, str)
                or not principal
                or len(principal) > 256
                or any(ord(character) < 33 or ord(character) == 127 for character in principal)
            ):
                raise ValueError('runtime principal Secret is outside the verified lease binding')
            principals.add(principal)
            bindings.append({
                'secret_name': name, 'secret_uid': registered[0]['actual_uid'],
                'principal_role': reference['principal_role'],
            })
        if len(principals) != 1:
            raise ValueError('credential references do not identify one runtime principal')
        principal_id = principals.pop()
        if self.principal_id is not None and self.principal_id != principal_id:
            raise ValueError('caller principal differs from lease-owned principal')
        self.principal_id = principal_id
        return {'principal_id': principal_id, 'credential_bindings': bindings}

    def _lease(self):
        lease = self.manager.store.load(self.lease_id)
        if validate_lease(lease) or lease['state'] != 'ready':
            raise ValueError('transaction requires a ready verified lease')
        if datetime.fromisoformat(lease['expires_at']) <= datetime.now(timezone.utc):
            raise ValueError('transaction lease expired')
        if lease['plan']['project_revision'] != self.project_revision:
            raise ValueError('lease project revision differs from transaction binding')
        return lease

    def _read_identity(self, lease):
        if not isinstance(self.principal_id, str) or not self.principal_id:
            raise ValueError('runtime principal has not been bound')
        provider = self.manager.providers.get(lease['provider'])
        if not isinstance(provider, KubernetesIsolationProvider):
            raise ValueError('transaction requires a Kubernetes application lease, not a cluster parent lease')
        locator = lease['runtime_locator']
        namespace = lease['plan']['source_namespace'] if lease['plan']['mode'] == 'adopted-test-replica' else lease['target_name']
        context = locator.get('kube_context')
        if not context or not locator.get('cluster_uid'):
            raise ValueError('Kubernetes lease runtime identity unavailable')
        def query(args):
            value, error = provider._json(lease['plan'], args, lease=lease)
            if error or not isinstance(value, dict):
                raise ValueError('runtime identity query failed')
            return value
        cluster = query(['get', 'namespace', 'kube-system'])
        ns = query(['get', 'namespace', namespace])
        svc = query(['-n', namespace, 'get', 'service', self.service])
        if cluster['metadata']['uid'] != locator['cluster_uid']:
            raise ValueError('lease cluster identity changed')
        if not any(p['port'] == self.port for p in svc['spec']['ports']):
            raise ValueError('service port outside bound service')
        registered = [x for x in lease['resources'] if x.get('kind') == 'Namespace' and x.get('name') == namespace]
        if len(registered) != 1 or not ns['metadata'].get('uid') or registered[0].get('actual_uid') != ns['metadata']['uid']:
            raise ValueError('namespace identity is outside lease')
        if not svc.get('metadata', {}).get('uid') or svc.get('spec', {}).get('type') == 'ExternalName':
            raise ValueError('service must have a local Kubernetes identity')
        if not isinstance(svc['spec'].get('selector'), dict) or not svc['spec']['selector']:
            raise ValueError('service requires namespace-local pod selectors')
        return {
            'lease_id': self.lease_id, 'cluster_uid': locator['cluster_uid'], 'namespace_uid': ns['metadata']['uid'],
            'namespace': namespace, 'context': context, 'service_uid': svc['metadata']['uid'], 'service': self.service,
            'principal_id': self.principal_id, 'project_revision': self.project_revision,
            'service_spec_sha256': canonical_hash(svc['spec']),
        }

    def open(self):
        from chaosatlas.oracles.replay import UrllibHttpTransport
        if self._tunnel is not None:
            raise ValueError('lease tunnel already opened')
        lease = self._lease()
        binding = self._read_identity(lease)
        ready = threading.Event()
        ports: list[int] = []
        self._tunnel = subprocess.Popen(
            ['kubectl', '--context', binding['context'], '-n', binding['namespace'], 'port-forward',
             f'svc/{self.service}', f':{self.port}', '--address', '127.0.0.1'],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
        def consume():
            assert self._tunnel and self._tunnel.stdout
            for line in self._tunnel.stdout:
                match = re.search(r'Forwarding from 127\.0\.0\.1:(\d+)', line)
                if match:
                    ports.append(int(match.group(1)))
                    ready.set()
            ready.set()
        threading.Thread(target=consume, daemon=True).start()
        if not ready.wait(30) or not ports:
            self.close()
            raise ValueError('lease service tunnel unavailable')
        binding['origin'] = f'http://127.0.0.1:{ports[0]}'
        self._binding = binding
        return UrllibHttpTransport(binding['origin'])

    @property
    def binding(self):
        if self._binding is None:
            raise ValueError('lease tunnel not opened')
        return deepcopy(self._binding)

    def verify(self, scope: dict[str, Any], transport) -> dict[str, str]:
        lease = self._lease()
        current = self._read_identity(lease)
        current['origin'] = self.binding['origin']
        if current != self.binding or self._tunnel is None or self._tunnel.poll() is not None:
            raise ValueError('runtime target changed or tunnel closed')
        if transport.base_url != current['origin'] or scope['service'] != current['service']:
            raise ValueError('HTTP target differs from lease binding')
        if scope['mode'] == 'disposable' and lease['plan']['mode'] == 'adopted-test-replica':
            raise ValueError('disposable transaction cannot use adopted database')
        digest = scope.get('image_digest')
        if not isinstance(digest, str) or not re.fullmatch(r'sha256:[a-f0-9]{64}', digest):
            raise ValueError('approved application image digest required')
        provider = self.manager.providers.get(lease['provider'])
        service, error = provider._json(lease['plan'], ['-n', current['namespace'], 'get', 'service', self.service], lease=lease)
        if error or canonical_hash((service or {}).get('spec')) != current['service_spec_sha256']:
            raise ValueError('service routing changed during verification')
        selector = service['spec']['selector']
        if any(not re.fullmatch(r'[A-Za-z0-9_./-]+', k) or not re.fullmatch(r'[A-Za-z0-9_.-]+', v) for k, v in selector.items()):
            raise ValueError('unsupported service selector')
        pods, error = provider._json(lease['plan'], ['-n', current['namespace'], 'get', 'pods', '-l', ','.join(f'{k}={v}' for k, v in sorted(selector.items()))], lease=lease)
        items = (pods or {}).get('items')
        if error or not isinstance(items, list) or not 1 <= len(items) <= 100:
            raise ValueError('bound application pods unavailable')
        for pod in items:
            statuses = pod.get('status', {}).get('containerStatuses', [])
            if not any(s.get('ready') is True and str(s.get('imageID', '')).split('@')[-1] == digest for s in statuses):
                raise ValueError('selected pod does not run approved ready image')
        return current

    def release(self):
        # Releasing an adopted namespace does not destroy its business objects.
        if self._lease()['plan']['mode'] == 'adopted-test-replica':
            raise ValueError('adopted release cannot prove object destruction')
        released = self.manager.release(self.lease_id)
        attempt = int(released.get('cleanup_attempts') or 0)
        audit_path = self.manager.store.audits / self.lease_id / f'cleanup-{attempt}.json'
        try:
            audit = json.loads(audit_path.read_text(encoding='utf-8-sig'))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError('environment release audit is unavailable') from exc
        if not verify_hash(audit, 'audit_sha256') or audit.get('lease_id') != self.lease_id or audit.get('status') != 'cleanup_verified':
            raise ValueError('environment release lacks verified isolation audit')
        return audit

    def close(self):
        if self._tunnel:
            self._tunnel.terminate()
            try:
                self._tunnel.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._tunnel.kill()
                self._tunnel.wait(timeout=5)
            if self._tunnel.stdout:
                self._tunnel.stdout.close()
            self._tunnel = None
