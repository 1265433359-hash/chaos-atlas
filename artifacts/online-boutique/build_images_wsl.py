#!/usr/bin/env python3
"""
Build Online Boutique service images locally (lab variant).
- Replaces gcr.io/distroless runtime base with alpine (Go static binaries).
- Keeps official Dockerfiles otherwise where bases are reachable.
- Sets GOPROXY to goproxy.cn + GOSUMDB=off (proxy.golang.org/sum.golang.org unreachable).
- For Node services: builds with node:20-alpine as runtime base (apk add nodejs would hang).
Builds are sequential; failures are recorded, not fatal.
"""
import os
import subprocess
import sys
import shutil

SRC = "/mnt/c/APP/project/chaos/online-boutique/src"
BUILD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "build")
os.makedirs(BUILD_DIR, exist_ok=True)

TAG_PREFIX = "online-boutique-lab"

GO_RUNTIME = "FROM alpine:3.22\n"
GO_ENTRYPOINT_OVERRIDES = {
    # (context, dockerfile_name, entry)
}

# dockerfiles keyed by service dir name: (kind, dockerfile content or None-to-copy)
# kind: go | node | python | dotnet | java

GO_SERVICES = ["checkoutservice", "frontend", "productcatalogservice", "shippingservice"]


def make_go_dockerfile(service, binary_out):
    """go: golang builder + alpine runtime (replace gcr.io/distroless)."""
    return f"""# Lab build: {service} (replaces gcr.io/distroless runtime with alpine)
FROM golang:1.26-alpine AS builder
WORKDIR /src
ENV GOFLAGS="-mod=mod" GOPROXY="https://goproxy.cn,direct" GOSUMDB=off CGO_ENABLED=0
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN go build -ldflags="-s -w" -o /{binary_out} .
FROM alpine:3.22
WORKDIR /src
COPY --from=builder /{binary_out} /src/{binary_out}
ENTRYPOINT ["/src/{binary_out}"]
"""


NODE_SERVICES = {
    "currencyservice": {"entry": "server.js", "run": "npm install --only=production"},
    "paymentservice": {"entry": "index.js", "run": "npm install --only=production"},
}


def make_node_dockerfile(service, entry):
    return f"""# Lab build: {service} (runtime node:20-alpine to avoid apk add nodejs)
FROM node:20-alpine
WORKDIR /usr/src/app
ENV NPM_CONFIG_REGISTRY="https://registry.npmjs.org"
COPY package*.json ./
RUN npm install --only=production
COPY . .
ENTRYPOINT ["node", "{entry}"]
"""


def make_python_dockerfile(service, entry, workdir):
    return f"""# Lab build: {service} (python:3.14-alpine)
FROM python:3.14-alpine
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_INDEX_URL="https://pypi.org/simple"
WORKDIR {workdir}
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
ENV PORT="8080"
EXPOSE 8080
ENTRYPOINT ["python", "{entry}"]
"""


EMAIL_REQUIREMENTS = "jinja2==3.1.5\nrequests==2.32.5\ngrpcio==1.76.0\ngrpcio-health-checking==1.76.0\nprotobuf==6.33.5\ngoogle-api-core==2.28.1\ngoogle-auth==2.23.4\nopentelemetry-api==1.39.1\nopentelemetry-sdk==1.39.1\nopentelemetry-exporter-otlp-proto-grpc==1.39.1\nopentelemetry-instrumentation-grpc==0.60b1\n"


def run(cmd, cwd, timeout=1800):
    print(f"\n>>> {' '.join(cmd)}")
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        tail = "\n".join((r.stdout or "").strip().splitlines()[-8:])
        if r.returncode != 0:
            tail += "\nSTDERR:\n" + "\n".join((r.stderr or "").strip().splitlines()[-8:])
        print(tail)
        return r.returncode == 0
    except subprocess.TimeoutExpired:
        print("TIMEOUT")
        return False


def build(service, tag, context):
    print(f"\n================ BUILD {service} ================")
    lab_df = os.path.join(context, "Dockerfile.lab")
    if os.path.exists(lab_df):
        return run(["docker", "build", "-f", "Dockerfile.lab", "-t", tag, context], cwd=context)
    return run(["docker", "build", "-t", tag, context], cwd=context)


def main():
    results = {}

    # 1) Go services
    for svc in GO_SERVICES:
        ctx = os.path.join(SRC, svc)
        df = make_go_dockerfile(svc, "server")
        df_path = os.path.join(ctx, "Dockerfile.lab")
        with open(df_path, "w", encoding="utf-8") as f:
            f.write(df)
        results[svc] = build(svc, f"{TAG_PREFIX}/{svc}:lab", ctx)

    # 2) Node services
    for svc, spec in NODE_SERVICES.items():
        ctx = os.path.join(SRC, svc)
        df = make_node_dockerfile(svc, spec["entry"])
        df_path = os.path.join(ctx, "Dockerfile.lab")
        with open(df_path, "w", encoding="utf-8") as f:
            f.write(df)
        results[svc] = build(svc, f"{TAG_PREFIX}/{svc}:lab", ctx)

    # 3) Python services
    # recommendationservice
    ctx = os.path.join(SRC, "recommendationservice")
    with open(os.path.join(ctx, "Dockerfile.lab"), "w", encoding="utf-8") as f:
        f.write(make_python_dockerfile("recommendationservice", "recommendation_server.py", "/recommendationservice"))
    results["recommendationservice"] = build("recommendationservice", f"{TAG_PREFIX}/recommendationservice:lab", ctx)

    # emailservice
    ctx = os.path.join(SRC, "emailservice")
    with open(os.path.join(ctx, "Dockerfile.lab"), "w", encoding="utf-8") as f:
        f.write(make_python_dockerfile("emailservice", "email_server.py", "/emailservice"))
    # patch requirements.txt to minimal (avoid full google deps needing compilation)
    req_path = os.path.join(ctx, "requirements.txt")
    shutil.copy2(req_path, req_path + ".orig")
    with open(req_path, "w", encoding="utf-8") as f:
        f.write(EMAIL_REQUIREMENTS)
    results["emailservice"] = build("emailservice", f"{TAG_PREFIX}/emailservice:lab", ctx)

    # 4) cartservice (.NET) — use official Dockerfile (mcr reachable), keep as-is
    ctx = os.path.join(SRC, "cartservice", "src")
    results["cartservice"] = build("cartservice", f"{TAG_PREFIX}/cartservice:lab", ctx)

    # 5) adservice (Java/Gradle) — official Dockerfile, bases reachable
    ctx = os.path.join(SRC, "adservice")
    results["adservice"] = build("adservice", f"{TAG_PREFIX}/adservice:lab", ctx)

    print("\n================ SUMMARY ================")
    for k, v in results.items():
        print(f"  {k:24s} {'OK' if v else 'FAIL'}")
    failed = [k for k, v in results.items() if not v]
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
