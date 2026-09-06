import pytest

from chaosatlas.oracles.ownership import OwnershipUncertain, select_owned


SPEC = {'collection_path': '$.items', 'max_items': 20,
        'complete': {'path': '$.total', 'operator': 'total_equals_length'},
        'identity': {'object_id': '$.id'}}
EXPECTED = {'$.marker': 'synthetic-run', '$.owner': 'synthetic-user', '$.parent': 'synthetic-room'}


def item(identifier='message-1', **changes):
    return {'id': identifier, 'marker': 'synthetic-run', 'owner': 'synthetic-user', 'parent': 'synthetic-room', **changes}


def test_exact_selection_skips_system_and_other_user_messages():
    result = select_owned({'items': [item('system', marker='join'), item('foreign', owner='other'), item()], 'total': 3}, SPEC, EXPECTED)
    assert result['identity'] == {'object_id': 'message-1'}


@pytest.mark.parametrize('payload', [
    {'items': [item(), item('message-2')], 'total': 2},
    {'items': [item()], 'total': 2},
    {'items': [item()], 'total': '1'},
    {'items': [item()]},
    {'items': [None], 'total': 1},
])
def test_ambiguous_incomplete_or_malformed_query_never_authorizes_deletion(payload):
    with pytest.raises(OwnershipUncertain):
        select_owned(payload, SPEC, EXPECTED)


def test_wrong_parent_or_marker_never_grants_ownership():
    result = select_owned({'items': [item(parent='foreign-room')], 'total': 1}, SPEC, EXPECTED)
    assert result['status'] == 'not_found'
    assert result['identity'] == {}
