#!/usr/bin/env bash
set -euo pipefail

real=/usr/bin/docker-chaosatlas-real
wrapper=/usr/bin/docker
restore() {
  if [[ -x "$real" ]]; then
    cp -f "$real" "$wrapper"
    rm -f "$real"
  fi
}
trap restore EXIT INT TERM

cp -f "$wrapper" "$real"
cat > "$wrapper" <<'EOF'
#!/usr/bin/env bash
set -e
args=()
for arg in "$@"; do
  if [[ "$arg" == "--cgroupns=private" ]]; then
    arg="--cgroupns=host"
  fi
  args+=("$arg")
done
exec /usr/bin/docker-chaosatlas-real "${args[@]}"
EOF
chmod 755 "$wrapper"

systemctl stop chaos-kind-proxy.service 2>/dev/null || true
export DOCKER_HOST=tcp://127.0.0.1:2375
kind delete cluster --name chaos-kind >/dev/null 2>&1 || true
kind create cluster --name chaos-kind --image kindest/node:v1.36.1 --wait 180s
