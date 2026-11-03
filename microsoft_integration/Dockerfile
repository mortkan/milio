FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libmariadb-dev pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY . /app/microsoft_integration/

# Run from project root so imports work
WORKDIR /

ENV PYTHONPATH=/

EXPOSE 8010

CMD ["uvicorn", "microsoft_integration.main:app", "--host", "0.0.0.0", "--port", "8010", "--log-level", "info"]
