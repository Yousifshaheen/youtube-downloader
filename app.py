"""Application entry point and factory for the YouTube Downloader service."""

from flask import Flask

from config import Config
from routes.download import download_bp
from routes.home import home_bp


def create_app(config_class: type = Config) -> Flask:
    """Create and configure the Flask application instance.

    Args:
        config_class: Configuration class to load settings from.

    Returns:
        A fully configured Flask application instance.
    """
    app = Flask(__name__)
    app.config.from_object(config_class)

    config_class.ensure_download_dir()

    app.register_blueprint(home_bp)
    app.register_blueprint(download_bp, url_prefix="/api")

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host=app.config["HOST"], port=app.config["PORT"], debug=app.config["DEBUG"])
