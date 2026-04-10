FROM mcr.microsoft.com/devcontainers/python:1-3.11-bullseye

# (Opcional pero recomendado) Actualizar paquetes del sistema
RUN apt-get update && export DEBIAN_FRONTEND=noninteractive \
    && apt-get -y install --no-install-recommends \
    build-essential \
    && apt-get clean -y && rm -rf /var/lib/apt/lists/*
