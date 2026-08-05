# Chaos workspace governance

The chaos workspace is versioned independently from the pinned
`train-ticket` source repository. The nested project remains at commit
`313886e99befb94be6cd45f085c98e0019f59829`; its own `.git` history is not
rewritten by experiments in this workspace.

Track together:

- `tools/` and `tools/tests/` (execution and validation logic)
- `raw_yaml/` (source mutation corpus)
- `artifacts/train-ticket/knowledge_base/` (retrieval cards and validation report)
- JSON/Markdown evidence required by the paper
- `task_plan.md`, `progress.md`, and `findings.md`

Do not track generated process logs, Python caches, credentials, or Secret
values. Every runtime result must retain the source mutation path, the pinned
project commit, the canonical classification report, and cleanup evidence.

Before publishing a result, run:

```text
python -m unittest discover -s tools/tests -v
python tools/validate_knowledge_base.py --root artifacts/train-ticket/knowledge_base
```

The root repository's first baseline commit is the audit boundary for future
version-drift checks. Historical reports are not silently rewritten; when an
implementation policy changes, record the new schema and the evidence limit in
`progress.md`.
