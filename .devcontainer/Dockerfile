FROM mcr.microsoft.com/devcontainers/python:3.12

WORKDIR /workspace
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Streamlit par défaut en headless en Codespace
ENV STREAMLIT_SERVER_HEADLESS=true
