import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    def __init__(self):
        self.gemini_api_key = os.getenv("GEMINI_API_KEY", "")
        self.gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
        self.groq_api_key = os.getenv("GROQ_API_KEY", "")
        self.groq_whisper_model = os.getenv("GROQ_WHISPER_MODEL", "whisper-large-v3-turbo")
        self.sarvam_api_key = os.getenv("SARVAM_API_KEY", "")
        self.sarvam_model = os.getenv("SARVAM_MODEL", "sarvam-105b")
        self.session_ttl_seconds = int(os.getenv("SESSION_TTL_SECONDS", "1800"))
        self.max_transcript_tokens = int(os.getenv("MAX_TRANSCRIPT_TOKENS", "60000"))
        self.analysis_token_limit = int(os.getenv("ANALYSIS_TOKEN_LIMIT", "45000"))
        self.analyze_rate_limit = os.getenv("ANALYZE_RATE_LIMIT", "8 per hour")
        self.port = int(os.getenv("FLASK_RUN_PORT", "5000"))
