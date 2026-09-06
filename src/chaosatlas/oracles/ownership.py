"""Exact ownership selection over bounded, complete response collections."""

from __future__ import annotations

from typing import Any

from chaosatlas.isolation.contracts import canonical_hash
from chaosatlas.oracles.transaction_contracts import _json_path


class OwnershipUncertain(ValueError):
    pass


def select_owned(payload: Any, spec: dict[str, Any], expected: dict[str, Any], *, expected_identity: dict[str, str] | None = None) -> dict[str, Any]:
    """Never pick an arbitrary first item; prove completeness and exact ownership."""
    if not expected or any(value is None for value in expected.values()):
        raise OwnershipUncertain('ownership requires nonempty explicit evidence')
    try:
        found = _json_path(payload, spec['collection_path'])
        collection = [found] if spec.get('single_object') else found
        if not isinstance(collection, list) or len(collection) > spec['max_items']:
            raise OwnershipUncertain('ownership collection is not bounded')
        if not spec.get('single_object'):
            complete = spec['complete']
            value = _json_path(payload, complete['path'])
            if complete['operator'] == 'total_equals_length':
                if type(value) is not int or value != len(collection):
                    raise OwnershipUncertain('ownership pagination incomplete')
            elif complete['operator'] == 'equals':
                if type(value) is not type(complete['expected']) or value != complete['expected']:
                    raise OwnershipUncertain('ownership pagination incomplete')
            else:
                raise OwnershipUncertain('unknown pagination contract')
        matches = []
        for item in collection:
            if not isinstance(item, dict):
                raise OwnershipUncertain('malformed ownership object')
            owned = all(_json_path(item, key) == value and type(_json_path(item, key)) is type(value) for key, value in expected.items())
            if expected_identity and all(_json_path(item, spec['identity'][key]) == value for key, value in expected_identity.items()) and not owned:
                raise OwnershipUncertain('persisted identity has different ownership')
            if owned:
                matches.append(item)
        if len(matches) > 1:
            raise OwnershipUncertain('ambiguous ownership: multiple exact matches')
        if not matches:
            return {'status': 'not_found', 'identity': {}, 'evidence_sha256': canonical_hash({'expected': expected, 'count': 0, 'complete': True})}
        identities = {name: _json_path(matches[0], path) for name, path in spec['identity'].items()}
        if not identities or any(not isinstance(x, str) or not x or len(x) > 256 for x in identities.values()):
            raise OwnershipUncertain('invalid owned identity')
        if expected_identity and identities != expected_identity:
            raise OwnershipUncertain('same marker points to a replacement identity')
        return {'status': 'owned', 'identity': identities, 'evidence_sha256': canonical_hash({'expected': expected, 'identity': identities, 'count': 1, 'complete': True})}
    except (KeyError, TypeError, IndexError) as exc:
        raise OwnershipUncertain('ownership evidence missing or malformed') from exc
