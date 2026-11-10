FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# PyMySQL does not require native MariaDB bindings; install the client runtime
# and certificates for the container environment.
RUN apt-get update \
    && apt-get install --no-install-recommends -y ca-certificates libmariadb3 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY settings.py main.py api.py avatars.py migrate.py ./

EXPOSE 8000

CMD ["sh", "-c", "python migrate.py && exec gunicorn --bind 0.0.0.0:8000 --workers 2 main:app"]
