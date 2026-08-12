# P02 Runtime Summary

The authorized P02 injection batch is complete. Every applied Chaos resource was deleted and verified absent. Runs with an unstable pre-injection baseline were retained but excluded from method statistics.

## Results

| Arm | Valid runs | Confirmed weakness | Protected target |
|---|---:|---|---|
| ChaosAtlas-KB-open | 3 | api-gateway, 2 reproductions | discovery-server, 1 valid run |
| ChaosAtlas-noKB-open | 4 | api-gateway, 2 reproductions | discovery-server, 2 reproductions |
| ChaosEater-adapter-open | 2 | api-gateway, 2 reproductions | not tested in open arm |

`api-gateway` is a confirmed weakness: it has one replica, and killing that Pod causes a repeatable business connection interruption or transient 500 before the replacement Pod becomes ready. The service recovers to HTTP 200 afterward.

`discovery-server` is a protected target in the valid noKB repetitions: the business oracle stayed HTTP 200 during the PodChaos lifecycle. This is defense evidence, not a claim that the component is risk-free.

The official ChaosEater track remains unavailable for P02 because the frozen project has no native Skaffold input. The adapter result is reported separately and is not treated as the official implementation.
