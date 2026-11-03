FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    AGENDA_HOST=0.0.0.0 \
    AGENDA_PORT=8000 \
    AGENDA_DB=/app/data/agenda.db \
    AGENDA_BACKUP_DIR=/app/data/backups

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p /app/data/backups

EXPOSE 8000
VOLUME ["/app/data"]

CMD ["python", "main.py"]
