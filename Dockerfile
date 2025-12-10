FROM python:3.14-slim

WORKDIR /app

# Install system dependencies
# sqlite3 is usually included, but explicit install prevents surprises
RUN apt-get update && apt-get install -y \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Install Python dependencies
# If 3.14 is very new, we add --prefer-binary to try and use older compatible wheels if specific 3.14 wheels aren't ready yet
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src/ .

# Command logic handled by docker-compose

  