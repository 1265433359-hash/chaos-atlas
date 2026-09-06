"""P4 lifecycle wiring tests use a synthetic Kubernetes executor only."""

from tools.kubernetes_lifecycle_executor import KubernetesLifecycleExecutor


class Workflow:
    def __init__(self):
        self.events = []

    def prepare_fixture(self, context):
        self.events.append(('prepare_fixture', context['run_id']))
        return {'status': 'prepared', 'cleanup_confirmed': False}

    def probe(self, phase, context):
        self.events.append(('probe', phase))
        return {'status': 'pass', 'samples': [{'status': 200}]}

    def collect_evidence(self, context):
        self.events.append(('collect_evidence', context['run_id']))
        return {'status': 'collected', 'evidence_refs': ['synthetic-test-only']}

    def cleanup_fixture(self, context):
        self.events.append(('cleanup_fixture', context['run_id']))
        return {'status': 'cleaned', 'cleanup_confirmed': True}


def test_executor_calls_one_workflow_oracle_in_complete_order(monkeypatch, tmp_path):
    workflow = Workflow()
    executor = KubernetesLifecycleExecutor(
        root=tmp_path, namespace='lab', allowed_namespaces={'lab'}, allow_live=True,
        oracle={'kind': 'http'},
        hooks={
            'prepare_fixture': workflow.prepare_fixture,
            'probe': workflow.probe,
            'collect_evidence': workflow.collect_evidence,
            'cleanup_fixture': workflow.cleanup_fixture,
            'gate': lambda manifest, path: {'decision': 'ready_for_injection', 'checks': {'target_pods': [{'name': 'api-0', 'uid': 'pod-1'}]}},
            'apply': lambda manifest: {'return_code': 0},
            'wait_lifecycle': lambda *args: (True, {'records': []}, []),
            'wait_target_ready': lambda *args: (True, 'ready', []),
            'delete': lambda *args: {'absent_confirmed': True},
            'cleanup_mesh': lambda **kwargs: {'confirmed': True},
        },
    )
    manifest = {
        'apiVersion': 'chaos-mesh.org/v1alpha1', 'kind': 'PodChaos',
        'metadata': {'name': 'synthetic-action', 'namespace': 'lab'},
        'spec': {'action': 'pod-kill', 'selector': {'namespaces': ['lab'], 'labelSelectors': {'app': 'api'}}},
    }
    result = executor.run(manifest, action_id='synthetic-action')
    assert result['status'] == 'executed'
    assert result['cleanup']['confirmed'] is True
    assert result['business_evidence']['status'] == 'collected'
    assert [event[0] for event in workflow.events] == ['prepare_fixture', 'probe', 'probe', 'collect_evidence', 'cleanup_fixture']
    assert workflow.events[0][1] == 'synthetic-action'


def test_fixture_prepare_failure_blocks_injection_and_records_no_cleanup(monkeypatch, tmp_path):
    events = []
    executor = KubernetesLifecycleExecutor(
        root=tmp_path, namespace='lab', allowed_namespaces={'lab'}, allow_live=True,
        hooks={
            'prepare_fixture': lambda context: events.append('prepare') or {'status': 'failed', 'reason_code': 'synthetic-test-only'},
            'gate': lambda manifest, path: {'decision': 'ready_for_injection', 'checks': {'target_pods': []}},
            'apply': lambda manifest: events.append('apply') or {'return_code': 0},
        },
    )
    manifest = {'kind': 'PodChaos', 'metadata': {'name': 'synthetic-action', 'namespace': 'lab'},
                'spec': {'action': 'pod-kill', 'selector': {'namespaces': ['lab'], 'labelSelectors': {'app': 'api'}}}}
    result = executor.run(manifest, action_id='synthetic-action')
    assert result['status'] == 'business_fixture_prepare_failed'
    assert events == ['prepare']
