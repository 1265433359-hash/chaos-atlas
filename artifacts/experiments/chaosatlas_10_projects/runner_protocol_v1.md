# Method-Neutral Runner v1

The runner owns namespace isolation, workload invocation, fault lifecycle, observation, recovery, cleanup, and evidence hashing. Method adapters only provide a ranked candidate list.

For each candidate, write immutable evidence for:

1. clean namespace and health gate;
2. deterministic baseline workload;
3. applied fault object and injection verification;
4. fixed observation window with HTTP/log/metric evidence;
5. fault removal and recovery health;
6. resource cleanup and absence check.

The runner must reject candidates whose target cannot be mapped to a live namespace-local workload. It must classify infrastructure failures as `environment_blocked` and malformed method output as `method_invalid`. No runner output is fed back into the selection prompt.
