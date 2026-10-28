FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN pip install --no-cache-dir -e . || true
RUN mkdir -p /app/data

ENV PROAGENT_DB_PATH=/app/data/proagent.db
ENV PROAGENT_LLM_PROVIDER=mock
ENV PROAGENT_HOST=0.0.0.0
ENV PROAGENT_PORT=8080

EXPOSE 8080

CMD ["uvicorn", "proagent_os.main:app", "--host", "0.0.0.0", "--port", "8080"]
