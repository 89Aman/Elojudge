"""Configuration settings for EloJudge."""

from __future__ import annotations

import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    # API Keys & Models
    api_key: str = os.getenv("GEMINI_API_KEY", os.getenv("LLM_API_KEY", ""))
    model: str = os.getenv("MODEL", "gemini-3.6-flash")
    model_cheap: str = os.getenv("MODEL_CHEAP", os.getenv("MODEL", "gemini-3.6-flash"))
    model_strong: str = os.getenv("MODEL_STRONG", "gemini-3.6-pro")

    # Google OAuth
    google_client_id: str = os.getenv(
        "GOOGLE_CLIENT_ID",
        "374080008653-c6a7ml4vgq9r22atrkvnugniff1k4r0s.apps.googleusercontent.com",
    )
    google_client_secret: str = os.getenv("GOOGLE_CLIENT_SECRET", "")

    # Storage (DigitalOcean PostgreSQL)
    database_url: str = os.getenv("DATABASE_URL", "")

    # Limits
    max_raw_items: int = int(os.getenv("MAX_RAW_ITEMS", "100"))
    max_clean_clusters: int = int(os.getenv("MAX_CLEAN_CLUSTERS", "30"))
    max_tournament_items: int = int(os.getenv("MAX_TOURNAMENT_ITEMS", "8"))
    pairs_per_request: int = int(os.getenv("PAIRS_PER_LLM_REQUEST", "2"))
    llm_timeout_seconds: int = int(os.getenv("LLM_TIMEOUT_SECONDS", "20"))

    # Default Job Budgets
    max_llm_requests_per_job: int = int(os.getenv("MAX_LLM_REQUESTS_PER_JOB", "12"))
    max_input_tokens_per_job: int = int(os.getenv("MAX_INPUT_TOKENS_PER_JOB", "50000"))
    max_output_tokens_per_job: int = int(os.getenv("MAX_OUTPUT_TOKENS_PER_JOB", "5000"))
    max_estimated_cost_per_job: float = float(os.getenv("MAX_ESTIMATED_COST_PER_JOB", "0.10"))
    max_retries_per_batch: int = int(os.getenv("MAX_RETRIES_PER_BATCH", "1"))

    # Pipeline Tuning
    near_duplicate_threshold: float = float(os.getenv("NEAR_DUPLICATE_THRESHOLD", "0.85"))
    enable_early_stopping: bool = os.getenv("ENABLE_EARLY_STOPPING", "true").lower() in ("true", "1", "yes")
    enable_local_decisions: bool = os.getenv("ENABLE_LOCAL_DECISIONS", "true").lower() in ("true", "1", "yes")
    local_decision_margin: float = float(os.getenv("LOCAL_DECISION_MARGIN", "0.35"))

    # Cost Estimation ($ per million tokens)
    cost_per_m_input_tokens: float = float(os.getenv("COST_PER_M_INPUT_TOKENS", "0.075"))
    cost_per_m_output_tokens: float = float(os.getenv("COST_PER_M_OUTPUT_TOKENS", "0.30"))


settings = Settings()
