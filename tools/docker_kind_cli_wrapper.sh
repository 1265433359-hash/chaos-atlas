#!/usr/bin/env bash
set -euo pipefail

args=()
for arg in "$@"; do
  if [[ "$arg" == "--cgroupns=private" ]]; then
    arg="--cgroupns=host"
  fi
  args+=("$arg")
done

exec /usr/bin/docker "${args[@]}"
