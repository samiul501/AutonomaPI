"""Process-wide settings, sourced from environment variables (see .env.example).

Kept as a plain dataclass instead of pydantic-settings to avoid an extra
dependency for what is, right now, a handful of scalar values.
"""

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()  # populates os.environ from backend/.env before the settings below read it


def _split_origins(raw: str) -> list[str]:
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


@dataclass(frozen=True)
class Settings:
    app_name: str = "AutonomaPI"
    cors_origins: list[str] = field(
        default_factory=lambda: _split_origins(os.getenv("CORS_ORIGINS", "http://localhost:3000"))
    )
    request_timeout_seconds: float = float(os.getenv("REQUEST_TIMEOUT_SECONDS", "15"))
    max_negative_cases_per_endpoint: int = int(os.getenv("MAX_NEGATIVE_CASES_PER_ENDPOINT", "50"))
    gemini_api_key: str | None = os.getenv("GEMINI_API_KEY") or None
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
    enable_llm_reasoning: bool = bool(os.getenv("GEMINI_API_KEY"))


settings = Settings()
