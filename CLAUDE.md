# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a FastAPI-based text-to-speech (TTS) server using Piper TTS for high-quality multilingual speech synthesis. The server provides a REST API for converting text to audio with support for Spanish, English, and Portuguese.

## Running the Server

### Using Docker (Recommended)
```bash
# Start the server with docker-compose
docker-compose up -d

# Build and run manually
docker build -t piper-tts-server .
docker run -d -p 8000:8000 -v ./models:/app/models piper-tts-server

# View logs
docker-compose logs -f

# Stop the server
docker-compose down
```

### Running Locally
```bash
# Install dependencies
pip install -r requirements.txt

# Run the server
python server.py
```

Server starts at `http://localhost:8000` by default.

## Configuration

Key configuration variables in `server.py`:

- `AUDIO_DIR`: Directory for generated audio files (default: `./generated_audio`)
- `MODELS_DIR`: Directory containing Piper .onnx model files (default: `./models`)
- `PIPER_EXECUTABLE`: Path to Piper executable (default: `"piper"`)
- `CLEANUP_INTERVAL`: Cleanup check interval in seconds (default: 300)
- `FILE_EXPIRY_TIME`: Audio file expiry time in seconds (default: 3600)
- `HOST`: Server host (default: `"0.0.0.0"` for Docker, `"localhost"` for local)
- `PUBLIC_HOST`: Public-facing URL host (can be overridden with `PUBLIC_HOST` env var)
- `PORT`: Server port (default: 8000)

## Architecture

### Core Components

**server.py**: Main FastAPI application with the following key components:

1. **Text Processing Pipeline** (lines 64-163):
   - `process_emojis()`: Converts emojis to periods for natural pauses
   - `clean_markdown()`: Removes markdown formatting (bold, italic, code blocks, links, etc.)
   - `enhance_punctuation_pauses()`: Adds spacing after punctuation for better prosody
   - `is_question()`: Detects questions in text
   - `enhance_questions()`: Adds ellipsis before question marks for natural pauses

2. **Audio Processing** (lines 166-248):
   - `apply_pitch_shift()`: Applies pitch shift to audio using pydub (especially for questions)
   - `convert_wav_to_mp3()`: Converts WAV to MP3 for better compression
   - `get_audio_info()`: Extracts audio metadata (duration, file size)

3. **API Endpoints**:
   - `GET /health`: Health check endpoint
   - `POST /synthesize`: Main TTS synthesis endpoint (lines 265-481)
   - `GET /audio/{filename}`: Static file serving for generated audio

4. **Background Tasks**:
   - `cleanup_old_files()`: Runs in a background thread, deletes expired audio files every 5 minutes

### Language and Model Mapping

The server supports three languages (lines 52-56):
- `"es"` → `es/es_MX-claude-high` (Spanish - Mexico)
- `"en"` → `en/en_GB-cori-high` (English - UK)
- `"pt"` → `pt/pt_BR-cadu-medium` (Portuguese - Brazil)

Models are stored in `./models/` directory with the structure:
```
models/
├── es/es_MX-claude-high.onnx
├── en/en_GB-cori-high.onnx
└── pt/pt_BR-cadu-medium.onnx
```

### Synthesis Process Flow

1. Text validation and language checking
2. Text preprocessing:
   - Clean markdown formatting
   - Convert emojis to periods
   - Enhance punctuation pauses
   - Detect and enhance questions
3. Generate unique filename (UUID)
4. Call Piper subprocess with dynamic parameters:
   - Questions: Higher noise-scale (0.65) and noise-w (0.85) for expressive intonation
   - Statements: Standard noise-scale (0.55) and noise-w (0.70)
   - Both: length-scale of 1.15 for slower, more natural speech
5. Monitor Piper subprocess resource usage (CPU, memory)
6. Apply pitch shift for questions (0.4 semitones upward)
7. Convert WAV to MP3 for compression
8. Return audio URL with metadata

### Resource Monitoring

The server monitors Piper subprocess performance (lines 366-407):
- CPU usage percentage (sampled every 100ms)
- Memory usage in MB (average and peak)
- Processing time in seconds
- Returns metrics in API response under `resources` field

## API Request/Response Format

### Synthesize Request
```json
{
  "text": "Hello, world! This is Piper speaking.",
  "language": "en"
}
```

### Synthesize Response
```json
{
  "status": "success",
  "audio_url": "http://localhost:8000/audio/{uuid}.mp3",
  "filename": "{uuid}.mp3",
  "format": "mp3",
  "language": "en",
  "model_used": "en/en_GB-cori-high",
  "resources": {
    "text_length": 42,
    "text_characters": 42,
    "processing_time_seconds": 1.23,
    "cpu_percent_average": 45.2,
    "memory_mb_average": 125.5,
    "memory_mb_peak": 130.2,
    "audio_duration_seconds": 3.5,
    "file_size_bytes": 56000,
    "file_size_kb": 54.69
  }
}
```

## Dependencies

- **fastapi**: Web framework
- **uvicorn**: ASGI server
- **pydantic**: Data validation
- **pydub**: Audio processing (pitch shift, WAV to MP3 conversion)
- **psutil**: Process and system monitoring
- **piper-tts**: External TTS engine (installed via Docker or system package)

## Docker Setup

The Dockerfile includes:
- Python 3.11-slim base image
- ffmpeg installation (required for pydub audio conversion)
- Piper TTS installation via pip
- Health check endpoint monitoring
- Volume mounts for models and generated audio

## Important Implementation Details

1. **UTF-8 Encoding**: Force UTF-8 on Windows (line 19) to handle multilingual text
2. **CORS Enabled**: All origins allowed for browser access
3. **File Cleanup**: Automatic cleanup thread runs every 5 minutes, deletes files older than 1 hour
4. **Timeout Protection**: Piper subprocess has 45-second timeout (line 393)
5. **Question Detection**: Questions get enhanced prosody parameters and pitch shifting
6. **Audio Compression**: All audio converted to MP3 after generation, WAV files deleted
7. **Unique Filenames**: UUID-based filenames prevent conflicts and allow concurrent requests

## Model Requirements

Models must be in ONNX format from Piper voices. Download from:
https://huggingface.co/rhasspy/piper-voices

Place model files in `./models/` directory following the language structure defined in `LANGUAGE_MODELS`.
