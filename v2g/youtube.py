import json
import re
import tempfile
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import requests
import yt_dlp

from v2g.text import seconds_to_timestamp


class YouTubeService:
    def __init__(self, config):
        self.config = config

    def extract_video(self, url):
        normalized = self.validate_url(url)
        options = {
            "quiet": True,
            "skip_download": True,
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": ["en", "en-US", "en.*"],
            "extract_flat": False,
        }
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(normalized, download=False)
        transcript = self.extract_caption_text(info)
        if not transcript:
            transcript = self.transcribe_audio(normalized)
        meta = {
            "title": info.get("title") or "Untitled video",
            "thumbnail": info.get("thumbnail") or "",
            "duration": info.get("duration") or 0,
            "duration_label": seconds_to_timestamp(info.get("duration") or 0),
            "video_id": info.get("id") or self.video_id_from_url(normalized),
            "url": normalized,
        }
        return {"meta": meta, "transcript": transcript}

    def validate_url(self, url):
        if not isinstance(url, str) or not url.strip():
            raise ValueError("Paste a YouTube URL to begin.")
        parsed = urlparse(url.strip())
        host = parsed.hostname or ""
        host = host.lower()
        allowed = host in {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}
        if not allowed:
            raise ValueError("Only youtube.com and youtu.be URLs are supported.")
        if host.endswith("youtube.com") and not parse_qs(parsed.query).get("v") and not parsed.path.startswith("/shorts/"):
            raise ValueError("The YouTube URL must include a video id.")
        if host == "youtu.be" and len(parsed.path.strip("/")) < 4:
            raise ValueError("The YouTube URL must include a video id.")
        return url.strip()

    def video_id_from_url(self, url):
        parsed = urlparse(url)
        if parsed.hostname == "youtu.be":
            return parsed.path.strip("/").split("/")[0]
        if parsed.path.startswith("/shorts/"):
            return parsed.path.split("/")[2]
        return parse_qs(parsed.query).get("v", [""])[0]

    def extract_caption_text(self, info):
        tracks = []
        for group in (info.get("subtitles") or {}, info.get("automatic_captions") or {}):
            for language, entries in group.items():
                if language.lower().startswith("en"):
                    tracks.extend(entries)
        tracks = sorted(tracks, key=lambda item: 0 if item.get("ext") == "vtt" else 1)
        for track in tracks:
            url = track.get("url")
            if not url:
                continue
            response = requests.get(url, timeout=20)
            response.raise_for_status()
            text = self.caption_payload_to_text(response.text, track.get("ext"))
            if text:
                return text
        return ""

    def caption_payload_to_text(self, payload, extension):
        if extension == "json3" or payload.lstrip().startswith("{"):
            return self.json3_to_text(payload)
        return self.vtt_to_text(payload)

    def json3_to_text(self, payload):
        data = json.loads(payload)
        parts = []
        for event in data.get("events", []):
            for segment in event.get("segs", []) or []:
                text = segment.get("utf8", "").strip()
                if text:
                    parts.append(text)
        return " ".join(parts)

    def vtt_to_text(self, payload):
        lines = []
        for line in payload.splitlines():
            clean = line.strip()
            if not clean or clean == "WEBVTT" or "-->" in clean or clean.isdigit():
                continue
            clean = re.sub(r"<[^>]+>", "", clean)
            clean = re.sub(r"&nbsp;", " ", clean)
            if clean:
                lines.append(clean)
        return " ".join(lines)

    def transcribe_audio(self, url):
        if not self.config.groq_api_key:
            raise ValueError("No captions were found. Configure GROQ_API_KEY to enable Groq Whisper fallback.")
        with tempfile.TemporaryDirectory(prefix=f"{uuid4()}-") as folder:
            target = str(Path(folder) / "%(id)s.%(ext)s")
            options = {
                "quiet": True,
                "format": "bestaudio/best",
                "outtmpl": target,
                "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3"}],
            }
            with yt_dlp.YoutubeDL(options) as ydl:
                ydl.download([url])
            audio_files = list(Path(folder).glob("*.mp3"))
            if not audio_files:
                raise ValueError("Audio extraction failed before speech-to-text.")
            with audio_files[0].open("rb") as audio:
                response = requests.post(
                    "https://api.groq.com/openai/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {self.config.groq_api_key}"},
                    data={"model": self.config.groq_whisper_model},
                    files={"file": (audio_files[0].name, audio, "audio/mpeg")},
                    timeout=600,
                )
            response.raise_for_status()
            data = response.json()
            transcript = data.get("text")
            if not transcript:
                raise ValueError("Groq Whisper did not return a transcript.")
            return transcript
