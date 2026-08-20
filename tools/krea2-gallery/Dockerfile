FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir fastapi==0.115.* "uvicorn[standard]==0.32.*" pillow==11.* python-multipart==0.0.*
COPY app/ /app/
ENV DATA_DIR=/data
EXPOSE 8020
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8020/healthz')"
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8020"]
