FROM python:3.12-alpine
WORKDIR /app
COPY server.py ./
USER 1000:1000
HEALTHCHECK --interval=15s --timeout=3s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8091/health',timeout=2).read()"
CMD ["python","server.py"]
