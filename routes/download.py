"""API routes for fetching video metadata and downloading media.

These routes contain no business logic of their own. They validate the
shape of incoming requests, delegate all YouTube/FFmpeg work to
``services.downloader``, and translate the results (or errors) into JSON
or file responses.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Union

from flask import Blueprint, Response, current_app, jsonify, request, send_file

from services.downloader import (
    DownloaderError,
    InvalidURLError,
    VideoUnavailableError,
    download_media,
    fetch_video_info,
)

download_bp = Blueprint("download", __name__)


def _ffmpeg_available() -> bool:
    """Check whether FFmpeg is installed and available on the system PATH."""
    return shutil.which("ffmpeg") is not None


def _cleanup_directory(directory: Path) -> None:
    """Remove a temporary download directory and all of its contents.

    Args:
        directory: Path to the directory to remove.
    """
    shutil.rmtree(directory, ignore_errors=True)


@download_bp.route("/info", methods=["POST"])
def get_video_info() -> Union[Response, tuple]:
    """Fetch metadata and available qualities for a YouTube video.

    Expects a JSON body: ``{"url": "<youtube-url>"}``.

    Returns:
        A JSON response containing video metadata and available qualities,
        or an error message with an appropriate HTTP status code.
    """
    payload = request.get_json(silent=True) or {}
    url = (payload.get("url") or "").strip()

    if not url:
        return jsonify({"success": False, "error": "Please provide a YouTube URL."}), 400

    try:
        info = fetch_video_info(url)
        return jsonify({"success": True, "data": info}), 200
    except InvalidURLError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except VideoUnavailableError as exc:
        return jsonify({"success": False, "error": str(exc)}), 404
    except DownloaderError as exc:
        return jsonify({"success": False, "error": str(exc)}), 502
    except Exception:
        current_app.logger.exception("Unexpected error while fetching video info")
        return jsonify(
            {"success": False, "error": "An unexpected error occurred. Please try again."}
        ), 500


@download_bp.route("/download", methods=["POST"])
def download_video() -> Union[Response, tuple]:
    """Download a YouTube video as MP4 or MP3 and stream it back to the client.

    Expects a JSON body::

        {
            "url": "<youtube-url>",
            "quality": "<height-in-pixels-or-'best'>",
            "format": "mp4" | "mp3"
        }

    Returns:
        The downloaded file as an attachment, or a JSON error response.
    """
    payload = request.get_json(silent=True) or {}
    url = (payload.get("url") or "").strip()
    quality = (payload.get("quality") or "best").strip()
    output_format = (payload.get("format") or "mp4").strip().lower()

    if not url:
        return jsonify({"success": False, "error": "Please provide a YouTube URL."}), 400

    if output_format not in current_app.config["ALLOWED_FORMATS"]:
        return jsonify({"success": False, "error": f"Unsupported format: {output_format}"}), 400

    if not _ffmpeg_available():
        return jsonify(
            {
                "success": False,
                "error": "FFmpeg is not installed on the server. Please install FFmpeg to enable downloads.",
            }
        ), 500

    try:
        file_path, download_name, work_dir = download_media(
            url=url,
            quality=quality,
            output_format=output_format,
            download_dir=current_app.config["DOWNLOAD_DIR"],
            audio_bitrate=current_app.config["AUDIO_BITRATE"],
        )
    except InvalidURLError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except VideoUnavailableError as exc:
        return jsonify({"success": False, "error": str(exc)}), 404
    except DownloaderError as exc:
        return jsonify({"success": False, "error": str(exc)}), 502
    except Exception:
        current_app.logger.exception("Unexpected error while downloading media")
        return jsonify(
            {"success": False, "error": "An unexpected error occurred during download."}
        ), 500

    response = send_file(file_path, as_attachment=True, download_name=download_name)
    response.call_on_close(lambda: _cleanup_directory(work_dir))
    return response
