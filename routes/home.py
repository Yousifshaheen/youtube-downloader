"""Routes for serving the main application page."""

from flask import Blueprint, render_template

home_bp = Blueprint("home", __name__)


@home_bp.route("/")
def index() -> str:
    """Render the main YouTube Downloader page."""
    return render_template("index.html")
