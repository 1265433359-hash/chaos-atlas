import os
import time
import argparse
from kubernetes import client, config

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", type=int, default=5, help="Duration in seconds")
    args = parser.parse_args()

    if os.getenv("KUBERNETES_SERVICE_HOST"):
        config.load_incluster_config()
    else:
        config.load_kube_config()

    v1 = client.AppsV1Api()
    namespace = "sock-shop"
    name = "front-end"
    available_replicas_list = []
    for i in range(args.duration):
        try:
            dep = v1.read_namespaced_deployment(name=name, namespace=namespace)
            available = dep.status.available_replicas or 0
            available_replicas_list.append(available)
            print("Time {}: availableReplicas={}".format(i+1, available))
        except Exception as e:
            print("Error at time {}: {}".format(i+1, e))
            available_replicas_list.append(None)
        if i < args.duration - 1:
            time.sleep(1)
    print("Summary over {} seconds: ".format(args.duration))
    print("Available replicas values: {}".format(available_replicas_list))
    if all(x == 1 for x in available_replicas_list):
        print("Steady state: front-end deployment has 1 available replica consistently.")
    elif any(x == 1 for x in available_replicas_list):
        print("Front-end deployment had some non-1 or missing replicas.")
    else:
        print("Front-end deployment has no available replicas.")

if __name__ == "__main__":
    main()