FROM python:3.12-alpine
WORKDIR /app
COPY server.py blocks.json gdd-blocks.json ./
USER 65534:65534
CMD ["python", "server.py"]
