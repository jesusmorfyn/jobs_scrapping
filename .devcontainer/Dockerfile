FROM mcr.microsoft.com/devcontainers/python:1-3.11-bullseye

# Eliminar el repositorio de Yarn que tiene la llave expirada
RUN rm -f /etc/apt/sources.list.d/yarn.list

# Instalar build-essential y SOLO las librerías necesarias para ChromeDriver (sin el navegador)
RUN apt-get update && export DEBIAN_FRONTEND=noninteractive \
    && apt-get -y install --no-install-recommends \
    build-essential \
    libglib2.0-0 libnss3 libxcb1 libx11-xcb1 libxcursor1 libxdamage1 \
    libxi6 libxtst6 libcups2 libxss1 libxrandr2 libasound2 \
    libpangocairo-1.0-0 libatk1.0-0 libatk-bridge2.0-0 libgtk-3-0 libgbm1 \
    && apt-get clean -y && rm -rf /var/lib/apt/lists/*