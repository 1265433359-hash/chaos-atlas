import os
import time
import argparse
from kubernetes import client, config
from unittest_base import K8sAPIBase

class TestCartsDbAvailableReplicas(K8sAPIBase):
    def __init__(self):
        super().__init__()
        self.apps_v1 = client.AppsV1Api()

    def test_carts_db_available_replicas(self, duration):
        # Record the availableReplicas of the carts-db deployment over the duration.
        observed = []
        for _ in range(duration):
            try:
                dep = self.apps_v1.read_namespaced_deployment_status(
                    name="carts-db", namespace="sock-shop"
                )
                available = dep.status.available_replicas
                if available is None:
                    available = 0
                observed.append(available)
                print(f"carts-db availableReplicas: {available}")
            except Exception as e:
                # A failed fetch counts as 0 available replicas per the threshold.
                observed.append(0)
                print(f"Error fetching carts-db deployment: {e}")
            time.sleep(1)

        # Compute the ratio of observations meeting the minimum availability.
        total = len(observed)
        success_count = sum(1 for x in observed if x >= 1)
        success_ratio = success_count / total if total > 0 else 0.0
        threshold_ratio = 0.95

        print("Summary:")
        print(f"Observed availableReplicas: {observed}")
        print(f"Observations with >=1 replica: {success_count}/{total} ({success_ratio:.2%})")
        print(f"Threshold: >=1 replica in at least {threshold_ratio:.0%} of observations")

        # Assert that the steady-state threshold is satisfied.
        assert success_ratio >= threshold_ratio, (
            f"Steady state violation: carts-db availableReplicas >= 1 in only "
            f"{success_count}/{total} observations ({success_ratio:.2%}), "
            f"which is below the required {threshold_ratio:.0%}"
        )
        print("PASS: carts-db availability meets the steady-state threshold.")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", type=int, default=5)
    args = parser.parse_args()
    test = TestCartsDbAvailableReplicas()
    test.test_carts_db_available_replicas(args.duration)

if __name__ == "__main__":
    main()