import os
import time
import argparse
from kubernetes import client, config
from unittest_base import K8sAPIBase

class SteadyStateTest(K8sAPIBase):
    def test_frontend_available_replicas(self, duration):
        # Create an AppsV1Api client using the same configuration loaded in K8sAPIBase.
        apps_v1 = client.AppsV1Api()
        namespace = "sock-shop"
        name = "front-end"

        observations = []  # Boolean list: True if availableReplicas >= 1
        consecutive_zeros = 0  # Current streak of observations with 0 available replicas
        max_consecutive_zeros = 0  # Maximum streak observed

        for i in range(duration):
            try:
                # Read the deployment's status to get available replicas.
                dep = apps_v1.read_namespaced_deployment(name=name, namespace=namespace)
                available = dep.status.available_replicas or 0
                ok = available >= 1
            except Exception as e:
                # On error, treat as unavailable (availableReplicas = 0) to be conservative.
                print("Error at time {}: {}".format(i + 1, e))
                available = 0
                ok = False

            observations.append(ok)

            # Update consecutive zero tracking.
            if ok:
                consecutive_zeros = 0
            else:
                consecutive_zeros += 1
                max_consecutive_zeros = max(max_consecutive_zeros, consecutive_zeros)

            print("Time {}: availableReplicas={} -> {}".format(i + 1, available, "OK" if ok else "NOT OK"))

            if i < duration - 1:
                time.sleep(1)

        total = len(observations)
        good = sum(observations)
        availability_ratio = good / total if total > 0 else 0

        # Threshold checks:
        # 1. availableReplicas >= 1 for at least 99% of the observations.
        meets_ratio = availability_ratio >= 0.99
        # 2. No dip to 0 lasting more than 1 consecutive second.
        meets_zero_tolerance = max_consecutive_zeros <= 1

        # Summary output for both success and failure cases.
        print()
        print("Summary over {} seconds:".format(duration))
        print("Total observations: {}".format(total))
        print("Observations with availableReplicas >= 1: {} ({:.2f}%)".format(good, availability_ratio * 100))
        print("Max consecutive zeros: {}".format(max_consecutive_zeros))
        print("Availability ratio threshold (>=99%): {}".format("PASS" if meets_ratio else "FAIL"))
        print("Consecutive zero threshold (<=1): {}".format("PASS" if meets_zero_tolerance else "FAIL"))

        # Assert both conditions to verify the steady state.
        assert meets_ratio, "Availability ratio {:.2f}% is below 99% threshold".format(availability_ratio * 100)
        assert meets_zero_tolerance, "Max consecutive zeros {} exceeds 1 second".format(max_consecutive_zeros)
        print("Steady-state threshold satisfied.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", type=int, default=5, help="Duration in seconds")
    args = parser.parse_args()

    # Instantiate the test class and run the steady-state check.
    test = SteadyStateTest()
    test.test_frontend_available_replicas(args.duration)


if __name__ == "__main__":
    main()
