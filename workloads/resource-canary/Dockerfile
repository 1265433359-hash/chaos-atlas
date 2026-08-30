FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    bash coreutils util-linux procps python3 ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -u 1000 -m chaosatlas

COPY server.py /opt/chaosatlas/server.py

USER 1000
ENTRYPOINT ["python3", "/opt/chaosatlas/server.py"]
