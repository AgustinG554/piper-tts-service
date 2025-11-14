import os
import subprocess
import uuid
import logging
import re
from pathlib import Path
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import threading
import time
import psutil
from pydub import AudioSegment

# Force UTF-8 encoding on Windows
os.environ["PYTHONIOENCODING"] = "utf-8"

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(title="Piper TTS Server", version="1.0.0")

# Add CORS middleware for browser access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration
AUDIO_DIR = Path("./generated_audio")
MODELS_DIR = Path("./models")  # Local models directory
PIPER_EXECUTABLE = "piper"  # Adjust if Piper is in a different location
CLEANUP_INTERVAL = 300  # 5 minutes
FILE_EXPIRY_TIME = 3600  # 1 hour in seconds
HOST = "0.0.0.0"  # Listen on all interfaces (required for Docker)
PORT = 8000

# Detect public URL (Railway, render.com, or custom)
if os.getenv("RAILWAY_PUBLIC_DOMAIN"):
    PUBLIC_URL = f"https://{os.getenv('RAILWAY_PUBLIC_DOMAIN')}"
elif os.getenv("RENDER_EXTERNAL_URL"):
    PUBLIC_URL = os.getenv("RENDER_EXTERNAL_URL")
elif os.getenv("PUBLIC_URL"):
    PUBLIC_URL = os.getenv("PUBLIC_URL")
else:
    PUBLIC_URL = f"http://localhost:{PORT}"

# Create directories
AUDIO_DIR.mkdir(exist_ok=True)
MODELS_DIR.mkdir(exist_ok=True)

# Language to model mapping
LANGUAGE_MODELS = {
    "es": "es/es_MX-claude-high",
    "en": "en/en_GB-cori-high",
    "pt": "pt/pt_BR-cadu-medium"
}


class SynthesizeRequest(BaseModel):
    text: str
    language: str


def process_emojis(text):
    """Convert emojis to periods (treats them as sentence endings for natural pauses)"""
    # Replace emojis with periods + space for natural pause and breathing
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # emoticons
        "\U0001F300-\U0001F5FF"  # symbols & pictographs
        "\U0001F680-\U0001F6FF"  # transport & map symbols
        "\U0001F700-\U0001F77F"  # alchemical symbols
        "\U0001F780-\U0001F7FF"  # Geometric Shapes Extended
        "\U0001F800-\U0001F8FF"  # Supplemental Arrows-C
        "\U0001F900-\U0001F9FF"  # Supplemental Symbols and Pictographs
        "\U0001FA00-\U0001FA6F"  # Chess Symbols
        "\U0001FA70-\U0001FAFF"  # Symbols and Pictographs Extended-A
        "\U00002702-\U000027B0"
        "\U000024C2-\U0001F251"
        "]+",
        flags=re.UNICODE
    )
    # Replace emojis with period + space (creates breathing space)
    text = emoji_pattern.sub('. ', text)
    # Clean up multiple periods - collapse to single period for better pausing
    text = re.sub(r'\.{2,}', '.', text)
    # Remove excessive spaces created by emoji conversion
    text = re.sub(r'\s{3,}', ' ', text)
    return text


def clean_markdown(text):
    """Remove all markdown formatting for TTS processing"""
    # Remove bold (**text** or __text__)
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
    text = re.sub(r'__(.*?)__', r'\1', text)

    # Remove italic (*text* or _text_)
    text = re.sub(r'\*(.*?)\*', r'\1', text)
    text = re.sub(r'_(.*?)_', r'\1', text)

    # Remove headers (# ## ###)
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)

    # Remove code blocks (```code```)
    text = re.sub(r'```[\s\S]*?```', '', text)
    text = re.sub(r'`([^`]+)`', r'\1', text)

    # Remove links [text](url) → text
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)

    # Remove bullet points (- or *)
    text = re.sub(r'^[\*\-]\s+', '', text, flags=re.MULTILINE)

    # Clean up extra spaces
    text = re.sub(r'\s{2,}', ' ', text)

    return text.strip()


def enhance_punctuation_pauses(text):
    """Add significant delays after punctuation for better breathing and pacing"""
    # Add extra spaces after punctuation - Piper uses spacing for pause duration
    # More spaces = longer pause (provides "breathing" room)

    # IMPORTANT: Don't process dots that are part of ellipsis (...)
    # Replace ... with a placeholder temporarily
    text = text.replace('...', '___ELLIPSIS___')

    # Handle periods, questions, exclamation marks with triple spaces (longer breath)
    # Match: punctuation optionally followed by spaces, then non-space or end of string
    text = re.sub(r'([.!?])(?:\s+|(?=[^\s])|$)', r'\1   ', text)

    # Handle commas and semicolons with double spaces (medium breath)
    text = re.sub(r'([,;])(?:\s+|(?=[^\s])|$)', r'\1  ', text)

    # Clean up excessive spaces (more than 4 consecutive spaces)
    text = re.sub(r'   {2,}', '   ', text)

    # Restore ellipsis
    text = text.replace('___ELLIPSIS___', '...')

    return text


def is_question(text):
    """Detect if text contains questions (Spanish: ¿...? or English: ...?)"""
    # Look for question marks (Spanish or English style)
    return bool(re.search(r'[¿?]', text))


def enhance_questions(text):
    """
    Enhance questions with ellipsis before question marks for natural pauses.
    Example: "¿Cómo estás?" → "¿Cómo estás...?"
    """
    # Add ellipsis before closing question marks (only if not already present)
    # Pattern: capture text before ?, add ... if not already there
    text = re.sub(r'([^.?!])[?]', r'\1...?', text)

    # Handle Spanish opening question marks - ensure they have proper spacing
    # Already handled by other functions, just ensure consistency
    return text


def apply_pitch_shift(wav_path, output_path, pitch_shift_semitones=0.3):
    """
    Apply subtle pitch shift to audio (especially useful for question endings).
    Positive semitones = pitch up (makes it sound more like a question)

    This uses pydub's simple method - for production, consider librosa or PyAudio
    """
    try:
        # Load the WAV file
        audio = AudioSegment.from_wav(str(wav_path))

        # Calculate the frame rate shift needed
        # Semitone ratio: 2^(semitones/12)
        import math
        pitch_ratio = 2 ** (pitch_shift_semitones / 12.0)

        # Resample to create pitch shift effect
        # New sample rate = original * pitch ratio
        new_frame_rate = int(audio.frame_rate * pitch_ratio)

        # Apply pitch shift by changing frame rate
        audio_shifted = audio._spawn(
            audio.raw_data,
            overrides={"frame_rate": new_frame_rate}
        )

        # Reset frame rate to original (pitch is now changed)
        audio_shifted = audio_shifted.set_frame_rate(audio.frame_rate)

        # Export to file
        audio_shifted.export(str(output_path), format="wav")
        logger.info(f"Pitch shift applied: {output_path}")

        return True
    except Exception as e:
        logger.error(f"Pitch shift failed: {str(e)}")
        # Return False but don't crash - we'll use original audio
        return False


def convert_wav_to_mp3(wav_path, mp3_path):
    """Convert WAV file to MP3 format for better compression"""
    try:
        logger.info(f"Converting {wav_path} to MP3...")
        audio = AudioSegment.from_wav(str(wav_path))
        audio.export(str(mp3_path), format="mp3", bitrate="192k")
        logger.info(f"MP3 conversion successful: {mp3_path}")

        # Delete original WAV file to save space
        wav_path.unlink()
        logger.info(f"Deleted original WAV file: {wav_path}")

        return True
    except Exception as e:
        logger.error(f"MP3 conversion failed: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to convert audio to MP3: {str(e)}"
        )


def get_audio_info(audio_path):
    """Get audio duration and file size information"""
    try:
        # Get file size in bytes
        file_size = audio_path.stat().st_size

        # Get audio duration using pydub
        audio = AudioSegment.from_mp3(str(audio_path))
        duration_seconds = len(audio) / 1000.0  # Convert milliseconds to seconds

        return {
            "duration_seconds": round(duration_seconds, 2),
            "file_size_bytes": file_size,
            "file_size_kb": round(file_size / 1024, 2)
        }
    except Exception as e:
        logger.error(f"Error getting audio info: {str(e)}")
        return {
            "duration_seconds": None,
            "file_size_bytes": audio_path.stat().st_size,
            "file_size_kb": round(audio_path.stat().st_size / 1024, 2)
        }


@app.on_event("startup")
async def startup_event():
    """Start the cleanup thread on app startup"""
    cleanup_thread = threading.Thread(target=cleanup_old_files, daemon=True)
    cleanup_thread.start()
    logger.info("Cleanup thread started")


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok", "service": "Piper TTS Server"}


@app.post("/synthesize")
async def synthesize(request: SynthesizeRequest):
    """
    Synthesize text to speech using Piper.

    Returns:
        JSON with audio_url pointing to the generated WAV file
    """
    try:
        # Validate input
        if not request.text or not request.text.strip():
            raise HTTPException(status_code=400, detail="Text cannot be empty")

        if not request.language or not request.language.strip():
            raise HTTPException(status_code=400, detail="Language must be specified")

        # Validate language is supported
        if request.language not in LANGUAGE_MODELS:
            available_languages = ", ".join(LANGUAGE_MODELS.keys())
            raise HTTPException(
                status_code=400,
                detail=f"Language '{request.language}' not supported. Available languages: {available_languages}"
            )

        # Step 1: Clean markdown formatting (remove **bold**, *italic*, etc.)
        text_without_markdown = clean_markdown(request.text)

        # Step 2: Process emojis - convert to periods for natural pauses
        clean_text = process_emojis(text_without_markdown).strip()

        if not clean_text:
            raise HTTPException(status_code=400, detail="Text cannot be empty after processing")

        # Enhance punctuation pauses - add slight delays after periods and commas
        # This creates natural breathing room while respecting user's punctuation
        text_with_pauses = enhance_punctuation_pauses(clean_text)

        # Detect if text contains questions for enhanced prosody
        contains_question = is_question(clean_text)

        # If text contains questions, enhance them with ellipsis for natural pauses
        if contains_question:
            text_with_pauses = enhance_questions(text_with_pauses)
            logger.info(f"Question detected - applying enhanced prosody")

        # Generate unique filename
        audio_filename = f"{uuid.uuid4()}.wav"
        audio_path = AUDIO_DIR / audio_filename

        # Get model path from language mapping
        model_name = LANGUAGE_MODELS[request.language]
        logger.info(f"Generating audio for: {clean_text[:50]}... with language: {request.language} (model: {model_name})")

        # Call Piper to generate audio
        try:
            # Build full path to model file
            model_path = MODELS_DIR / f"{model_name}.onnx"

            # Verify model exists
            if not model_path.exists():
                raise HTTPException(
                    status_code=400,
                    detail=f"Model file not found: {model_path}. Please ensure the model file exists in the models directory."
                )

            # Track resource usage during audio generation
            start_time = time.time()

            # Piper syntax with voice parameters for expressive, emotional speech with pauses
            # --length-scale: Controls speed. Default 1.0 (normal), lower = faster, higher = slower
            # --noise-scale: Controls pitch/tone variation (intonation/emotion). Default 0.667. Higher = more expressive
            # --noise-w: Controls phoneme duration variation (naturalness). Default 0.333. Higher = more expressive

            # Dynamic parameters based on whether text contains questions
            # Questions get higher noise-scale and noise-w for more expressive intonation
            if contains_question:
                noise_scale = "0.65"  # Increased from 0.55 for more tonal variation in questions
                noise_w = "0.85"      # Increased from 0.70 for more natural rhythm and expressiveness
                length_scale = "1.15" # Same speed
                logger.info(f"Using enhanced parameters for question: noise-scale={noise_scale}, noise-w={noise_w}")
            else:
                noise_scale = "0.55"  # Standard variation for statements
                noise_w = "0.70"      # Standard naturalness
                length_scale = "1.15" # Standard speed

            process = subprocess.Popen(
                [
                    PIPER_EXECUTABLE,
                    "--model", str(model_path),
                    "--output_file", str(audio_path),
                    "--length-scale", length_scale,
                    "--noise-scale", noise_scale,
                    "--noise-w", noise_w
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8"
            )

            # Monitor Piper subprocess resource usage in background thread
            cpu_samples = []
            memory_samples = []
            monitoring = True

            def monitor_subprocess_resources():
                """Monitor CPU and memory usage of Piper subprocess in background"""
                try:
                    piper_psutil = psutil.Process(process.pid)
                    piper_psutil.cpu_percent(interval=None)  # Initialize baseline

                    while monitoring:
                        try:
                            cpu_samples.append(piper_psutil.cpu_percent(interval=0.1))
                            memory_samples.append(piper_psutil.memory_info().rss / 1024 / 1024)  # MB
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            break
                        time.sleep(0.1)
                except Exception as e:
                    logger.warning(f"Could not monitor Piper subprocess: {str(e)}")

            # Start monitoring thread
            monitor_thread = threading.Thread(target=monitor_subprocess_resources, daemon=True)
            monitor_thread.start()

            # Run Piper subprocess with input and wait for completion
            try:
                stdout, stderr = process.communicate(input=text_with_pauses, timeout=45)
            finally:
                # Stop monitoring thread
                monitoring = False
                monitor_thread.join(timeout=2)

            # Calculate resource usage averages
            end_time = time.time()
            processing_time = round(end_time - start_time, 2)

            # Calculate averages from samples
            avg_cpu_percent = round(sum(cpu_samples) / len(cpu_samples), 1) if cpu_samples else 0.0
            avg_memory_mb = round(sum(memory_samples) / len(memory_samples), 2) if memory_samples else 0.0
            peak_memory_mb = round(max(memory_samples), 2) if memory_samples else 0.0

            if process.returncode != 0:
                logger.error(f"Piper error: {stderr}")
                raise HTTPException(
                    status_code=500,
                    detail=f"Piper synthesis failed: {stderr}"
                )

            if not audio_path.exists():
                raise HTTPException(
                    status_code=500,
                    detail="Audio file was not generated"
                )

            logger.info(f"Audio generated successfully: {audio_filename}")

            # Apply pitch shift for questions (makes them sound more interrogative)
            if contains_question:
                pitch_shifted_path = AUDIO_DIR / f"{uuid.uuid4()}_pitched.wav"
                if apply_pitch_shift(audio_path, pitch_shifted_path, pitch_shift_semitones=0.4):
                    # Replace original with pitch-shifted version
                    audio_path.unlink()  # Delete original
                    pitch_shifted_path.rename(audio_path)  # Rename pitched to original name
                    logger.info(f"Pitch shift applied to question: {audio_filename}")
                else:
                    logger.warning(f"Pitch shift failed, using original audio for: {audio_filename}")

            # Convert WAV to MP3
            mp3_filename = f"{uuid.uuid4()}.mp3"
            mp3_path = AUDIO_DIR / mp3_filename
            convert_wav_to_mp3(audio_path, mp3_path)

            # Construct URL for MP3 file using PUBLIC_URL (accessible from outside)
            audio_url = f"{PUBLIC_URL}/audio/{mp3_filename}"

            # Get audio information
            audio_info = get_audio_info(mp3_path)

            return {
                "status": "success",
                "audio_url": audio_url,
                "filename": mp3_filename,
                "format": "mp3",
                "language": request.language,
                "model_used": model_name,
                "resources": {
                    "text_length": len(clean_text),
                    "text_characters": len(request.text),
                    "processing_time_seconds": processing_time,
                    "cpu_percent_average": avg_cpu_percent,
                    "memory_mb_average": avg_memory_mb,
                    "memory_mb_peak": peak_memory_mb,
                    "audio_duration_seconds": audio_info.get("duration_seconds"),
                    "file_size_bytes": audio_info.get("file_size_bytes"),
                    "file_size_kb": audio_info.get("file_size_kb")
                }
            }

        except subprocess.TimeoutExpired:
            raise HTTPException(
                status_code=500,
                detail="Piper synthesis timed out (took longer than 30 seconds)"
            )
        except FileNotFoundError:
            raise HTTPException(
                status_code=500,
                detail=f"Piper executable not found at '{PIPER_EXECUTABLE}'. Please ensure Piper is installed and in PATH"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


def cleanup_old_files():
    """Periodically delete audio files older than FILE_EXPIRY_TIME"""
    while True:
        try:
            now = datetime.now()
            cutoff_time = now - timedelta(seconds=FILE_EXPIRY_TIME)

            deleted_count = 0
            for audio_file in AUDIO_DIR.glob("*.mp3"):
                file_time = datetime.fromtimestamp(audio_file.stat().st_mtime)
                if file_time < cutoff_time:
                    audio_file.unlink()
                    deleted_count += 1

            if deleted_count > 0:
                logger.info(f"Cleanup: Deleted {deleted_count} old audio files")

        except Exception as e:
            logger.error(f"Error during cleanup: {str(e)}")

        time.sleep(CLEANUP_INTERVAL)


# Mount static files for audio serving
# This must be done after defining routes to avoid conflicts
app.mount("/audio", StaticFiles(directory=str(AUDIO_DIR)), name="audio")


if __name__ == "__main__":
    import uvicorn
    logger.info(f"Starting Piper TTS Server")
    logger.info(f"API accessible at: {PUBLIC_URL}")
    logger.info(f"Audio files will be stored in: {AUDIO_DIR.absolute()}")
    logger.info(f"Loading models from: {MODELS_DIR.absolute()}")
    logger.info(f"(Set PUBLIC_URL environment variable to override external URL)")
    uvicorn.run(app, host=HOST, port=PORT)
