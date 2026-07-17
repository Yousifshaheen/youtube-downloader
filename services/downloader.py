"""Core YouTube extraction and download logic built on top of yt-dlp.

All interaction with yt-dlp and FFmpeg is isolated in this module so that
Flask routes stay thin and free of business logic.
"""

from __future__ import annotations

import re
import shutil
import uuid
from pathlib import Path
from typing import Any, Optional

import yt_dlp

_YOUTUBE_URL_PATTERN = re.compile(
    r"^(https?://)?(www\.)?(m\.)?"
    r"(youtube\.com/(watch\?v=|shorts/|embed/|live/)|youtu\.be/)[\w\-]+",
    re.IGNORECASE,
)

# Only these "standard" heights are ever surfaced to the frontend, even if
# yt-dlp exposes odd intermediate encodes for a given video.
_STANDARD_HEIGHTS: tuple = (144, 240, 360, 480, 720, 1080, 1440, 2160, 4320)

_UNAVAILABLE_MARKERS: tuple = (
    "private video",
    "video unavailable",
    "sign in to confirm your age",
    "age-restricted",
    "this video is not available",
    "has been removed",
    "account associated with this video has been terminated",
    "content isn't available",
)


class DownloaderError(Exception):
    """Base exception for all downloader-related failures."""


class InvalidURLError(DownloaderError):
    """Raised when the supplied URL is not a valid YouTube URL."""


class VideoUnavailableError(DownloaderError):
    """Raised when the requested video is private, removed, or restricted."""


def _validate_url(url: str) -> None:
    """Validate that the given string is a well-formed YouTube URL.

    Args:
        url: The URL to validate.

    Raises:
        InvalidURLError: If the URL is not a recognizable YouTube URL.
    """
    if not _YOUTUBE_URL_PATTERN.match(url.strip()):
        raise InvalidURLError("Please provide a valid YouTube URL.")


def _translate_download_error(exc: Exception) -> DownloaderError:
    """Translate a yt-dlp exception into a domain-specific downloader error.

    Args:
        exc: The original exception raised by yt-dlp.

    Returns:
        A ``DownloaderError`` subclass with a clear, user-facing message.
    """
    message = str(exc).lower()

    for marker in _UNAVAILABLE_MARKERS:
        if marker in message:
            return VideoUnavailableError(
                "This video is unavailable. It may be private, age-restricted, or removed."
            )

    if "unable to download webpage" in message or "urlopen error" in message:
        return DownloaderError("Network error while contacting YouTube. Please try again.")

    return DownloaderError("Failed to process the video. Please check the URL and try again.")


def _base_ydl_opts() -> dict[str, Any]:
    """Build the baseline yt-dlp options shared by all operations."""
    return {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "nocheckcertificate": True,
    }


def _extract_available_heights(formats: list[dict[str, Any]]) -> list[int]:
    """Determine which standard video quality heights are available.

    Args:
        formats: The list of format dictionaries returned by yt-dlp.

    Returns:
        A sorted list of available heights (e.g. ``[360, 720, 1080]``),
        restricted to the standard set of resolutions.
    """
    available_heights = {
        fmt["height"]
        for fmt in formats
        if fmt.get("vcodec") not in (None, "none") and fmt.get("height")
    }
    return sorted(height for height in _STANDARD_HEIGHTS if height in available_heights)


def _format_duration(seconds: Optional[int]) -> str:
    """Format a duration in seconds as HH:MM:SS or MM:SS.

    Args:
        seconds: Duration in seconds.

    Returns:
        A human-readable duration string.
    """
    if not seconds:
        return "Unknown"

    hours, remainder = divmod(int(seconds), 3600)
    minutes, secs = divmod(remainder, 60)

    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def _format_upload_date(date_str: Optional[str]) -> str:
    """Format a yt-dlp upload date (``YYYYMMDD``) as ``YYYY-MM-DD``.

    Args:
        date_str: Raw upload date string from yt-dlp.

    Returns:
        A formatted date string, or ``"Unknown"`` if unavailable.
    """
    if not date_str or len(date_str) != 8:
        return "Unknown"
    return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"


def fetch_video_info(url: str) -> dict[str, Any]:
    """Fetch metadata and available qualities for a YouTube video without downloading it.

    Args:
        url: The YouTube video URL.

    Returns:
        A dictionary containing title, thumbnail, channel, duration,
        upload date, view count, and a list of available quality heights.

    Raises:
        InvalidURLError: If the URL is not a valid YouTube URL.
        VideoUnavailableError: If the video cannot be accessed.
        DownloaderError: For any other extraction failure.
    """
    _validate_url(url)

    options = _base_ydl_opts()
    options["skip_download"] = True

    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=False)
    except yt_dlp.utils.DownloadError as exc:
        raise _translate_download_error(exc) from exc

    if info is None:
        raise VideoUnavailableError("This video is unavailable.")

    formats = info.get("formats") or []
    qualities = _extract_available_heights(formats)

    return {
        "title": info.get("title", "Unknown title"),
        "thumbnail": info.get("thumbnail", ""),
        "channel": info.get("channel") or info.get("uploader") or "Unknown channel",
        "duration": _format_duration(info.get("duration")),
        "upload_date": _format_upload_date(info.get("upload_date")),
        "views": info.get("view_count"),
        "qualities": qualities,
    }


def _build_video_format_selector(quality: str) -> str:
    """Build a yt-dlp format selector string for a requested video quality.

    YouTube's highest-quality audio track is frequently Opus packed in a
    WebM container. FFmpeg can remux that straight into an MP4 file, but
    many players (Windows' default player, some smart TVs, older browsers)
    cannot decode Opus audio inside an MP4 wrapper, even though the video
    plays fine. To guarantee broad compatibility, this selector prefers an
    MP4 video track paired with an M4A (AAC) audio track — both natively
    MP4-compatible, so FFmpeg only needs to remux, not re-encode. It falls
    back to the plain best-video/best-audio combination only if no
    MP4+M4A pairing is available for that resolution.

    Args:
        quality: The requested height as a string (e.g. ``"1080"``), or ``"best"``.

    Returns:
        A yt-dlp format selector that picks the best compatible video/audio
        pair at or below the requested height, merged via FFmpeg.
    """
    if quality == "best" or not quality.isdigit():
        return (
            "bestvideo[ext=mp4]+bestaudio[ext=m4a]/"
            "bestvideo+bestaudio/best"
        )

    height = int(quality)
    return (
        f"bestvideo[height<={height}][ext=mp4]+bestaudio[ext=m4a]/"
        f"bestvideo[height<={height}]+bestaudio/best[height<={height}]"
    )


def download_media(
    url: str,
    quality: str,
    output_format: str,
    download_dir: Path,
    audio_bitrate: str = "192",
) -> tuple[Path, str, Path]:
    """Download a YouTube video as MP4 or MP3 into an isolated temporary directory.

    Args:
        url: The YouTube video URL.
        quality: Requested video height (e.g. ``"1080"``) or ``"best"``. Ignored for MP3.
        output_format: Either ``"mp4"`` or ``"mp3"``.
        download_dir: Base directory under which a temporary work directory is created.
        audio_bitrate: Target audio bitrate in kbps for MP3 extraction.

    Returns:
        A tuple of ``(file_path, download_name, work_dir)`` where ``work_dir``
        is the temporary directory that should be deleted once the file has
        been served to the client.

    Raises:
        InvalidURLError: If the URL is not a valid YouTube URL.
        VideoUnavailableError: If the video cannot be accessed.
        DownloaderError: For any other download or conversion failure.
    """
    _validate_url(url)

    work_dir = download_dir / uuid.uuid4().hex
    work_dir.mkdir(parents=True, exist_ok=True)

    output_template = str(work_dir / "%(title).100s.%(ext)s")

    options = _base_ydl_opts()
    options["outtmpl"] = output_template

    if output_format == "mp3":
        options["format"] = "bestaudio/best"
        options["postprocessors"] = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": audio_bitrate,
            }
        ]
    else:
        options["format"] = _build_video_format_selector(quality)
        options["merge_output_format"] = "mp4"

    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            ydl.extract_info(url, download=True)
    except yt_dlp.utils.DownloadError as exc:
        shutil.rmtree(work_dir, ignore_errors=True)
        raise _translate_download_error(exc) from exc
    except Exception as exc:
        shutil.rmtree(work_dir, ignore_errors=True)
        raise DownloaderError("Failed to download media. Please try again.") from exc

    produced_files = [f for f in work_dir.iterdir() if f.is_file()]

    if not produced_files:
        shutil.rmtree(work_dir, ignore_errors=True)
        raise DownloaderError("Download completed but no output file was produced.")

    file_path = produced_files[0]
    download_name = file_path.name

    return file_path, download_name, work_dir
