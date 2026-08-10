# v1.2 Candidate Registry Freeze

Status: `frozen`
Protocol: `heldout_protocol_v1_2`
Freeze date: 2026-08-10

The registry is a deterministic concatenation of the three already frozen static project pools. No experiment result, verdict, ranking, or post-injection knowledge was used to filter it.

| Project | Candidates | Protected | Unprotected | Unknown |
|---|---:|---:|---:|---:|
| HOTEL | 16 | 0 | 16 | 0 |
| SOCIALNET | 44 | 16 | 12 | 16 |
| TEASTORE | 23 | 0 | 7 | 16 |
| **Pooled** | **83** | **16** | **35** | **32** |

All pooled quotas pass and every project contributes at least 8 legal candidates. Candidate IDs are unique. Protected remains `descriptive_only` because only SOCIALNET contributes protected candidates.

Artifacts:

- `heldout_v12_candidate_registry.json`
- `heldout_v12_freeze_snapshot.json`

The registry freeze does not authorize deployment or injection. Method/runner/seed/cleanup freeze and bring-up gates remain pending.
