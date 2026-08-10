# Held-out v1.2 Adapter Freeze

Status: `static_configured_runtime_validation_pending`

This artifact defines the project-specific boundary consumed by the common
dry-run runner. It is an input description, not an execution authorization.
Every endpoint below is tied to a fixed source commit. No runtime result or
oracle label is included.

| Project | Entry | Health contract | Business oracle | Runtime status |
|---|---|---|---|---|
| HOTEL | `frontend:5000` in `heldout-hotel-lab` | `GET /` | `GET /hotels` with fixture parameters | not_run; fixture required |
| SOCIALNET | `nginx-thrift:8080` in `heldout-socialnet-lab` | `GET /` | `POST /wrk2-api/post/compose` | not_run; user fixture required |
| TEASTORE | `teastore-webui:8080` in `heldout-teastore-lab` | `GET /tools.descartes.teastore.webui/ready/isready` | `GET /tools.descartes.teastore.webui/` | not_run |

The source evidence is respectively `delimitrou/DeathStarBench` at
`6ecb09706140f8730b5385c08f1386c654c3c526` for Hotel/SOCIALNET and
`DescartesResearch/TeaStore` at
`34b37f7e7be433ce72d5f9455e66922a13116749` for TeaStore. Detailed paths and
request assertions are in the JSON artifact.

## Gate

Before `execution_ready` can be changed, each project must pass a runtime-only
check consisting of port-forward, two stable baselines, health probe, business
oracle, observation collection, one-fault recovery, and no active Chaos Mesh
resource after cleanup. A failed cleanup invalidates the run. No candidate YAML,
method, seed, quota, or result may be changed during that check.

The current artifact intentionally keeps `execution_ready=false` for all three
projects. No cluster, deployment, Chaos Mesh resource, or formal run was
started by this stage.
