# Progress

2026-08-10: Created an isolated plan for the selection-only ablation. Existing user and agent changes are preserved. No runtime or LLM work has started under this plan.

2026-08-10: Added frozen selection-only protocol, clean bundle/prompt builder, strict runner, status report, and claim-evidence matrix. The builder generated 48 files for 36 selection records; all 12 leakage audits passed and seed-specific prompt hashes differ. The runner preflight passed but real selection is blocked because no API credential is present. No LLM call or runtime work was performed.

2026-08-10: Added static-oracle analyzer. It reports `blocked_missing_or_invalid_selection_outputs` with 0/36 valid records, as expected. Targeted tests passed (13 passed); full suite passed with repository-local basetemp: 239 passed, 5 subtests passed, 1 existing pytest cache warning. The default full suite still hits two Windows global-temp ACL errors, unrelated to this work.

2026-08-10: A user-launched run produced a duplicate ledger entry for ESHOP/blind/pilot/1001. The runner was stopped at 3 ledger entries to prevent further API cost. Partial outputs are retained but excluded; the runner now defaults to isolated run `run-20260810-r2` and refuses overwrites.

2026-08-10: Corrected run `run-20260810-r2` completed 36/36 valid selections with 36 unique ledger keys and no invalid records. Static analysis completed: SOCIALNET full-pre formal protected-waste mean 0.033 vs blind 0.433; unprotected-selection fraction 0.967 vs 0.567. ESHOP partial-pre formal unprotected-selection fraction 0.333 vs blind 0.167; protected-waste is non-informative because ESHOP has zero protected oracle candidates. Full test suite passed with repository-local basetemp: 241 passed, 5 subtests passed, 1 existing pytest cache warning.

2026-08-10: Updated stale status and claim-evidence records to reflect the completed 36/36 selection run. A read-only TeaStore feasibility check found kubectl available but no reachable Docker daemon and no kind CLI; TeaStore is recorded as `environment_blocked` without deployment or injection. Frozen pools and mutation YAMLs remain untouched.

2026-08-10: Final consistency check passed: selection ledger contains 36 unique valid records; analysis JSON and TeaStore feasibility JSON parse successfully; held-out v1.2 feasibility checker and targeted tests pass.

2026-08-10: Read-only Kubernetes check found configured contexts `kind-chaos-kind` and `docker-desktop`, but both API servers refused connection. Runtime Gate 3 remains blocked by infrastructure, with no deployment or fault injection attempted.

2026-08-10: User reported starting Docker; follow-up read-only check found Docker Desktop processes present but `com.docker.service` stopped, both Docker named pipes unavailable, and `docker info` timing out. Engine is not ready yet; no system service was started by the agent.

2026-08-10: WSL diagnosis: `Ubuntu` and `docker-desktop` are both WSL2 `Running`; Docker Desktop CLI reports `Status=starting`, but no Docker socket is created. This indicates a stuck Docker Desktop backend rather than a stopped WSL distribution.

2026-08-10: Authorized Docker restart completed: backend processes were replaced and WSL was shut down/restarted. Docker Desktop created a new session but remained `starting`; `com.docker.service` stayed stopped and `Start-Service` failed with Win32 code 1077. Runtime work remains blocked pending administrator-level Docker startup or Windows reboot.

2026-08-10: Post-admin diagnostic: Docker backend log reports repeated engine init-control `/ping` timeouts and HTTP 500 for over an hour. WSL2 distributions are running, but no Docker engine socket is available; no Podman/nerdctl alternative is installed. Runtime execution remains blocked pending Docker Desktop repair/reset or a separate cluster.
