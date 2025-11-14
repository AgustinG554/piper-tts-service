#!/usr/bin/env python3
"""
Download Piper TTS models from HuggingFace if they don't exist or are corrupted.
This ensures models are available even if Git LFS fails.
"""
import os
import sys
import urllib.request
from pathlib import Path

# Model configurations: (local_path, huggingface_url)
MODELS = {
    "es/es_MX-claude-high.onnx": "https://huggingface.co/rhasspy/piper-voices/resolve/main/es/es_MX/claude/high/es_MX-claude-high.onnx",
    "es/es_MX-claude-high.onnx.json": "https://huggingface.co/rhasspy/piper-voices/resolve/main/es/es_MX/claude/high/es_MX-claude-high.onnx.json",
    "en/en_GB-cori-high.onnx": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/cori/high/en_GB-cori-high.onnx",
    "en/en_GB-cori-high.onnx.json": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/cori/high/en_GB-cori-high.onnx.json",
    "pt/pt_BR-cadu-medium.onnx": "https://huggingface.co/rhasspy/piper-voices/resolve/main/pt/pt_BR/cadu/medium/pt_BR-cadu-medium.onnx",
    "pt/pt_BR-cadu-medium.onnx.json": "https://huggingface.co/rhasspy/piper-voices/resolve/main/pt/pt_BR/cadu/medium/pt_BR-cadu-medium.onnx.json",
}

MODELS_DIR = Path("./models")
MIN_VALID_SIZE = 1_000_000  # 1 MB - anything smaller is likely an LFS pointer


def is_valid_model(filepath: Path) -> bool:
    """Check if model file exists and is not an LFS pointer."""
    if not filepath.exists():
        return False

    size = filepath.stat().st_size
    if size < MIN_VALID_SIZE:
        print(f"⚠️  {filepath} is too small ({size} bytes) - likely an LFS pointer")
        return False

    return True


def download_file(url: str, dest_path: Path):
    """Download a file from URL to destination path."""
    print(f"📥 Downloading {dest_path.name}...")
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        urllib.request.urlretrieve(url, dest_path)
        size_mb = dest_path.stat().st_size / (1024 * 1024)
        print(f"✓ Downloaded {dest_path.name} ({size_mb:.2f} MB)")
    except Exception as e:
        print(f"❌ Failed to download {dest_path.name}: {e}")
        sys.exit(1)


def main():
    """Download models if they don't exist or are corrupted."""
    print("Checking Piper TTS models...")

    needs_download = False

    for local_path, url in MODELS.items():
        filepath = MODELS_DIR / local_path

        if not is_valid_model(filepath):
            needs_download = True
            download_file(url, filepath)

    if not needs_download:
        print("✓ All models are valid and ready to use")
    else:
        print("\n✓ Model download complete!")


if __name__ == "__main__":
    main()
