FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY dumper.py ./
COPY webapp/ webapp/
ENV PORT=8010 HOST=0.0.0.0 PYTHONUNBUFFERED=1
EXPOSE 8010
# /data is the mounted dump root. Read-only viewing needs no API creds;
# live mode reads API_ID/API_HASH from the environment -- pass them at runtime
# (docker run -e API_ID=... -e API_HASH=..., or via docker-compose/.env). Never bake them in.
CMD ["python", "webapp/server.py", "/data"]
