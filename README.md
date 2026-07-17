# YouTube Downloader

A production-ready web application for fetching YouTube video metadata and
downloading videos as **MP4** (any available resolution, up to 8K) or
**MP3** (192 kbps audio). Built with Flask, yt-dlp, and FFmpeg on the
backend, and vanilla HTML/CSS/JS on the frontend — no frameworks, no
build step.

> **Important:** Only download content you own or have the right to
> download (your own uploads, Creative Commons material, public domain
> content, etc.). Respect YouTube's Terms of Service and applicable
> copyright law in your jurisdiction.

## Project structure

```
youtube-downloader/
├── app.py                 # Flask application factory / entry point
├── config.py               # Centralized configuration
├── routes/
│   ├── home.py              # Serves the frontend page
│   └── download.py          # /api/info and /api/download endpoints
├── services/
│   └── downloader.py        # All yt-dlp / FFmpeg logic lives here
├── templates/
│   └── index.html
├── static/
│   ├── css/style.css
│   ├── js/script.js
│   └── images/
├── downloads/                # Temporary download staging (auto-cleaned)
├── requirements.txt
├── .gitignore
└── README.md
```

## How it works

1. The user pastes a YouTube URL and clicks **Get Video**.
2. The frontend calls `POST /api/info`, which uses yt-dlp to fetch
   metadata (title, thumbnail, channel, duration, upload date, views)
   **without downloading anything**, and returns only the quality
   heights that are actually available for that video.
3. The user picks a quality and a format (MP4 or MP3) and clicks
   **Download**.
4. `POST /api/download` downloads the media into a unique temporary
   folder under `downloads/`:
   - **MP4:** yt-dlp selects the best video stream at or below the
     chosen resolution and the best available audio stream, then uses
     FFmpeg to mux them into a single `.mp4` file (this is required for
     1080p and above, where YouTube serves video and audio separately).
   - **MP3:** yt-dlp downloads the best audio stream and FFmpeg
     transcodes it to a 192 kbps MP3.
5. The file is streamed back to the browser as an attachment. Once the
   response finishes sending, the server automatically deletes the
   temporary folder — nothing is left behind in `downloads/`.

## 1. Prerequisites

- Python 3.13 or newer
- FFmpeg (required for merging video/audio and for MP3 conversion)

### Installing FFmpeg

**macOS (Homebrew):**
```bash
brew install ffmpeg
```

**Ubuntu / Debian:**
```bash
sudo apt update
sudo apt install ffmpeg
```

**Windows:**
1. Download a build from https://www.gyan.dev/ffmpeg/builds/ (the
   "release essentials" zip is enough).
2. Extract it, e.g. to `C:\ffmpeg`.
3. Add `C:\ffmpeg\bin` to your `PATH` environment variable.
4. Open a new terminal and verify with `ffmpeg -version`.

**Verify installation (any OS):**
```bash
ffmpeg -version
```
The app checks for FFmpeg automatically at download time and returns a
clear error if it isn't found.

## 2. Installation

```bash
# Clone or unzip the project, then cd into it
cd youtube-downloader

# Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

## 3. Running the app (development)

```bash
python app.py
```

By default this starts the server at `http://0.0.0.0:5000`. Open
`http://localhost:5000` in your browser.

Environment variables you can set (all optional):

| Variable       | Default     | Description                          |
|----------------|-------------|---------------------------------------|
| `FLASK_HOST`   | `0.0.0.0`   | Interface to bind to                  |
| `FLASK_PORT`   | `5000`      | Port to listen on                     |
| `FLASK_DEBUG`  | `0`         | Set to `1` to enable debug/reload     |
| `SECRET_KEY`   | dev key     | Set a real secret key in production   |

## 4. Running in production

Never use the Flask development server in production. Use a WSGI
server such as **Gunicorn** behind a reverse proxy such as **Nginx**.

```bash
pip install gunicorn
gunicorn --workers 4 --bind 0.0.0.0:8000 --timeout 300 app:app
```

`--timeout 300` is important: large 4K/8K downloads and MP3 conversions
can take longer than Gunicorn's default 30-second worker timeout.

### Example Nginx reverse proxy config

```nginx
server {
    listen 80;
    server_name your-domain.com;

    client_max_body_size 5m;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }
}
```

### Running as a systemd service

```ini
# /etc/systemd/system/yt-downloader.service
[Unit]
Description=YouTube Downloader
After=network.target

[Service]
User=www-data
WorkingDirectory=/opt/youtube-downloader
Environment="SECRET_KEY=change-me-to-a-real-secret"
ExecStart=/opt/youtube-downloader/venv/bin/gunicorn --workers 4 --bind 0.0.0.0:8000 --timeout 300 app:app
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now yt-downloader
```

### Docker (optional)

```dockerfile
FROM python:3.13-slim

RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

EXPOSE 8000
CMD ["gunicorn", "--workers", "4", "--bind", "0.0.0.0:8000", "--timeout", "300", "app:app"]
```

```bash
docker build -t youtube-downloader .
docker run -p 8000:8000 youtube-downloader
```

## 5. Notes on maintenance

- **Keep yt-dlp up to date.** YouTube changes its site frequently, and
  yt-dlp ships fixes often. Run `pip install -U yt-dlp` regularly, or
  pin a CI job to bump it.
- **Disk space:** the `downloads/` directory is cleaned automatically
  after each request completes, but if the process is killed mid-download
  a stray temp folder can be left behind. Consider a periodic cron job
  (`find downloads -mindepth 1 -maxdepth 1 -mmin +60 -exec rm -rf {} +`)
  as a safety net on long-running deployments.
- **Rate limiting:** if you expose this publicly, put a rate limiter
  (e.g. Flask-Limiter or an Nginx `limit_req` zone) in front of
  `/api/download` to avoid abuse.
