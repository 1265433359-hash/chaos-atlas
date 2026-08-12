#!/usr/bin/env bash
set -u
for i in $(seq 1 30); do
  date -u +%H:%M:%S
  docker inspect chaos-kind-control-plane --format 'status={{.State.Status}} running={{.State.Running}} exit={{.State.ExitCode}} restart={{.RestartCount}} mode={{.HostConfig.CgroupnsMode}}' 2>&1 || true
  sleep 1
done
