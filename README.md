# Piper TTS Server

A FastAPI-based text-to-speech server using Piper for high-quality speech synthesis.

## Features

- **REST API** for text-to-speech synthesis
- **Auto-cleanup** of generated audio files (configurable expiry time)
- **Static file serving** for easy audio playback
- **CORS enabled** for browser access
- **Health check** endpoint for monitoring
- **Error handling** with detailed error messages
- **Docker support** for easy deployment with all dependencies included

## Quick Start with Docker (Recommended)

The easiest way to run the server is with Docker, which includes ffmpeg and Piper TTS automatically:

```bash
# Using docker-compose (easiest)
docker-compose up -d

# Or build and run manually
docker build -t piper-tts-server .
docker run -d -p 8000:8000 -v ./models:/app/models piper-tts-server
```

Then access the API at `http://localhost:8000`

**For detailed Docker instructions, see [DOCKER.md](DOCKER.md)**

---

## Installation

### Prerequisites

1. **Piper** - Download from [Piper releases](https://github.com/rhasspy/piper/releases)

   - Download the executable for your OS
   - Add it to PATH or note its location

2. **Piper Models** - Download models from [Piper models](https://huggingface.co/rhasspy/piper-voices)

   - Models should be accessible to Piper (in a known directory)
   - Note the model path/name for API requests

3. **Python 3.8+** - Required for the server

### Setup

1. Install Python dependencies:

```bash
pip install -r requirements.txt
```

2. Ensure Piper is accessible:
   - On Linux/Mac: `piper` should be in PATH
   - On Windows: Either add to PATH or update `PIPER_EXECUTABLE` in `server.py`

## Configuration

Edit `server.py` to customize:

```python
AUDIO_DIR = Path("./generated_audio")      # Directory for generated audio
PIPER_EXECUTABLE = "piper"                 # Path to Piper executable
CLEANUP_INTERVAL = 300                     # Cleanup check interval (seconds)
FILE_EXPIRY_TIME = 3600                    # Audio file expiry time (seconds, default 1 hour)
HOST = "localhost"                         # Server host
PORT = 8000                                # Server port
```

## Running the Server

```bash
python server.py
```

The server will start at `http://localhost:8000`

## API Endpoints

### Health Check

```
GET /health
```

Returns:

```json
{
  "status": "ok",
  "service": "Piper TTS Server"
}
```

### Synthesize Text to Speech

```
POST /synthesize
```

**Request body:**

```json
{
  "text": "Hello, world! This is Piper speaking.",
  "model": "en_US-lessac-medium"
}
```

**Response:**

```json
{
  "status": "success",
  "audio_url": "http://localhost:8000/audio/abc123def-4567-89ab-cdef-0123456789ab.wav",
  "filename": "abc123def-4567-89ab-cdef-0123456789ab.wav",
  "model": "en_US-lessac-medium"
}
```

### Audio File Access

```
GET /audio/{filename}
```

Returns the WAV audio file for playback or download.

## Example Usage

### Using curl

```bash
curl -X POST http://localhost:8000/synthesize \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello world", "model": "en_US-lessac-medium"}'
```

### Using Python

```python
import requests

response = requests.post(
    "http://localhost:8000/synthesize",
    json={
        "text": "Hello world",
        "model": "en_US-lessac-medium"
    }
)

data = response.json()
print(f"Audio URL: {data['audio_url']}")
```

### Using JavaScript/Fetch

```javascript
fetch("http://localhost:8000/synthesize", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
  },
  body: JSON.stringify({
    text: "Hello world",
    model: "en_US-lessac-medium",
  }),
})
  .then((response) => response.json())
  .then((data) => {
    console.log("Audio URL:", data.audio_url);
    // Play audio in browser
    const audio = new Audio(data.audio_url);
    audio.play();
  });
```

## Available Models

Common Piper models:

- `en_US-lessac-medium` - English (US) - Medium quality
- `en_US-lessac-high` - English (US) - High quality
- `en_GB-alba-medium` - English (UK) - Medium quality
- `fr_FR-siwis-medium` - French - Medium quality
- `de_DE-thorsten-medium` - German - Medium quality
- `es_ES-carlfm-medium` - Spanish - Medium quality

For a complete list, check [Piper Voices](https://huggingface.co/rhasspy/piper-voices)

## File Management

- Generated audio files are stored in `./generated_audio/`
- Files are automatically deleted after `FILE_EXPIRY_TIME` (default: 1 hour)
- The cleanup process runs every `CLEANUP_INTERVAL` (default: 5 minutes)
- Each file has a unique UUID filename to prevent conflicts

## Troubleshooting

### "Piper executable not found"

- Ensure Piper is installed
- Verify it's in PATH: `which piper` (Linux/Mac) or `where piper` (Windows)
- Update `PIPER_EXECUTABLE` path in `server.py`

### "Audio file was not generated"

- Check if the model exists and is accessible
- Verify the text is not empty
- Check logs for Piper error messages

### "Piper synthesis timed out"

- The synthesis took longer than 30 seconds
- Try with shorter text or a faster model

### Models not found

- Ensure models are downloaded and in Piper's model directory
- By default Piper looks in `~/.local/share/piper/models/` (Linux/Mac) or AppData (Windows)
- You can configure model path in Piper

## Performance Notes

- First request may take longer as Piper loads the model
- Subsequent requests are faster (model stays in memory)
- Audio generation time depends on text length and model
- Temporary files are automatically cleaned up to save disk space

## License

This server wrapper is provided as-is. Piper is licensed under Apache License 2.0.

This service uses the "claude (es_MX)" voice model from HirCoir / Piper-TTS-Spanish,
licensed under the Apache License 2.0.
See https://huggingface.co/spaces/HirCoir/Piper-TTS-Spanish

Voice model "cori (high)" – English (UK) female voice.
Dataset derived from LibriVox recordings (public domain).
Model by Bryce Beattie (https://brycebeattie.com), licensed as Public Domain.
