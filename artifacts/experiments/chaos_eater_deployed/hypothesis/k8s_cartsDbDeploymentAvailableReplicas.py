import os
import time
import argparse
from kubernetes import client, config

def check_carts_db_available_replicas(duration):
    if os.getenv('KUBERNETES_SERVICE_HOST'):
        config.load_incluster_config()
    else:
        config.load_kube_config()
    v1 = client.AppsV1Api()
    observed = []
    for _ in range(duration):
        try:
            dep = v1.read_namespaced_deployment_status(name='carts-db', namespace='sock-shop')
            available = dep.status.available_replicas
            observed.append(available)
            print(f"carts-db availableReplicas: {available}")
        except Exception as e:
            observed.append(None)
            print(f"Error fetching carts-db deployment: {e}")
        time.sleep(1)
    print("Summary:")
    print(f"Observed availableReplicas: {observed}")
    exact_one = all(x == 1 for x in observed if x is not None) and len(observed) > 0 and None not in observed
    print(f"Exactly 1 available replica: {exact_one}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--duration', type=int, default=5)
    args = parser.parse_args()
    check_carts_db_available_replicas(args.duration)
