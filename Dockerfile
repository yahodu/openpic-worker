FROM python:3.10-slim

WORKDIR /app

# Install system deps for OpenCV/PIL
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    g++ \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy code
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY worker.py .

# Create mount point for persistent volume
RUN mkdir -p /data/insightface

CMD ["python", "worker.py"]
