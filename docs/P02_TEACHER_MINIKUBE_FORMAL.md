# P02 Teacher Minikube Formal Runtime Batch

This procedure creates a new evidence set on the teacher Minikube cluster. It
does not reuse or overwrite the earlier WSL/kind runtime results.

## Scope

- `ChaosAtlas-KB-open`: 2 generated mutations, 3 repetitions each.
- `ChaosAtlas-noKB-open`: 2 generated mutations, 3 repetitions each.
- `ChaosEater-adapter-open`: 1 generated mutation, 3 repetitions.
- Total: 15 independent runs. Identical fault YAML from different arms remains
  separately executed and attributed.

`ChaosEater-adapter-open` is supplementary. It is not the official ChaosEater
workflow. P02 still lacks the root Skaffold input required by official
ChaosEater, so these results cannot support an official-ChaosEater claim.

## Safety Gates

Every run fails closed unless all of the following hold:

- the original `kubectl` context and node identity remain unchanged;
- the read-only P02 execution gate passes;
- no PodChaos, NetworkChaos, or StressChaos exists anywhere in the cluster;
- every P02 Deployment and Pod is stable and Ready;
- at least five business-oracle baseline requests return HTTP 200;
- Chaos Mesh confirms injection;
- the killed target is replaced by a new Ready Pod UID;
- the business oracle returns HTTP 200 after recovery;
- the injected resource is deleted and global cleanup is confirmed.
- after cleanup, the oracle is observed for at least 60 seconds and the final
  10 samples must be consecutive HTTP 200 responses before another run starts.

The batch stops after the first failed run and never overwrites an existing
report.

The sustained post-cleanup window attributes delayed service-registration or
cache effects to the mutation that caused them. It also prevents those effects
from contaminating the next arm's baseline.

## Commands

After pulling the commit on the teacher computer, inspect the 15-run plan:

```powershell
python .\tools\run_p02_formal_batch.py
```

Start the formal batch only while all P02 and Chaos Mesh Pods are healthy:

```powershell
python .\tools\run_p02_formal_batch.py --execute
```

Reports are written below:

```text
artifacts/experiments/chaosatlas_10_projects/runtime_results/P02/teacher-minikube-formal/
```

Do not rerun into the same directory after a partial or completed batch. Keep
that evidence immutable and select a new `--output` path for a new batch.
