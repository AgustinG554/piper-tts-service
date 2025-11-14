# Use official Python runtime as base image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies including git and git-lfs
RUN apt-get update && apt-get install -y \
    ffmpeg \
    build-essential \
    curl \
    git \
    git-lfs \
    && rm -rf /var/lib/apt/lists/*

# Install Piper TTS
RUN pip install --no-cache-dir piper-tts

# Copy requirements file
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code and model downloader
COPY server.py .
COPY download_models.py .

# Copy model files (LFS files will be included if properly checked out)
COPY models models

# Download models from HuggingFace if LFS files are not available
RUN python download_models.py

# Create directory for audio
RUN mkdir -p /app/generated_audio

# Expose port for the API
EXPOSE 8000

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONIOENCODING=utf-8

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run the application
CMD ["python", "server.py"]
