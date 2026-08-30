FROM python:3.12-slim

RUN useradd -u 1000 -m chaosatlas
WORKDIR /opt/chaosatlas
COPY server.py /opt/chaosatlas/server.py
COPY http-boundary-capability /opt/chaosatlas/http-boundary-capability
RUN chmod 0444 /opt/chaosatlas/http-boundary-capability
USER 1000
ENTRYPOINT ["python", "/opt/chaosatlas/server.py"]
