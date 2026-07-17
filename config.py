"""Application configuration for the YouTube Downloader service."""

import os
from pathlib import Path


class Config:
    """Base configuration for the Flask application."""

    BASE_DIR: Path = Path(__file__).resolve().parent
    DOWNLOAD_DIR: Path = BASE_DIR / "downloads"

    # Requests only ever carry a URL + a couple of short strings as JSON.
    MAX_CONTENT_LENGTH: int = 64 * 1024  # 64 KB

    ALLOWED_FORMATS: tuple = ("mp4", "mp3")

    AUDIO_BITRATE: str = "192"

    SECRET_KEY: str = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")

    DEBUG: bool = os.environ.get("FLASK_DEBUG", "0") == "1"

    HOST: str = os.environ.get("FLASK_HOST", "0.0.0.0")
    PORT: int = int(os.environ.get("FLASK_PORT", "5000"))

    @classmethod
    def ensure_download_dir(cls) -> None:
        """Ensure the downloads directory exists on disk."""
        cls.DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
