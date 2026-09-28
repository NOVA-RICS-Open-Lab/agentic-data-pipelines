FROM python:3.12-slim

RUN apt-get update && apt-get install -y docker.io && rm -rf /var/lib/apt/lists/*
ADD --chmod=755 https://github.com/docker/compose/releases/download/v2.29.7/docker-compose-linux-x86_64 /usr/local/lib/docker/cli-plugins/docker-compose

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir .

COPY src ./src
COPY a2a_server.py .

ENV PYTHONPATH=/app

EXPOSE 8000

CMD ["python", "-m", "src.main"]