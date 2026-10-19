from pathlib import Path
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "postgresql+psycopg://documind:documind@localhost:5432/documind"
    api_keys: dict[str, UUID] = Field(default_factory=dict)
    legacy_api_enabled: bool = True
    bff_service_key: SecretStr = SecretStr('')
    registration_mode: Literal['disabled', 'invite'] = 'disabled'
    account_base_url: str = 'https://localhost:8443'
    smtp_host: str = ''
    smtp_port: int = Field(465, ge=1, le=65535)
    smtp_username: str = ''
    smtp_password: SecretStr = SecretStr('')
    smtp_from: str = 'no-reply@localhost'
    smtp_starttls: bool = False
    reset_ttl_seconds: int = Field(900, ge=60, le=3600)
    requests_per_minute: int = Field(120, ge=10)
    uploads_per_minute: int = Field(5, ge=1)
    max_documents_per_owner: int = Field(100, ge=1)
    max_storage_bytes_per_owner: int = Field(500 * 1024 * 1024, ge=1024)
    ai_max_concurrent_per_owner: int = Field(1, ge=1, le=4)
    storage_dir: Path = Path("var/documents")
    max_upload_bytes: int = Field(10 * 1024 * 1024, gt=0)
    max_pdf_pages: int = Field(200, gt=0)
    max_text_chars: int = Field(1_000_000, gt=0)
    worker_timeout_seconds: float = Field(30, gt=0)
    worker_memory_mb: int = Field(512, ge=128)
    max_concurrent_workers: int = Field(2, ge=1, le=16)
    chunk_chars: int = Field(1500, ge=100)
    ai_enabled: bool = False
    ai_provider: Literal['openai', 'mock'] = 'openai'
    openai_api_key: SecretStr = SecretStr('')
    openai_model: str = 'gpt-5.6-luna'
    ai_budget_usd: Decimal = Field(Decimal('4'), ge=0, le=100)
    ai_summary_quota: int = Field(20, ge=0)
    ai_question_quota: int = Field(100, ge=0)
    ai_max_input_tokens: int = Field(16000, ge=4000, le=64000)
    ai_max_output_tokens: int = Field(1200, ge=256, le=4000)
    ai_max_summary_steps: int = Field(5, ge=1, le=8)
    ai_max_question_chunks: int = Field(5, ge=1, le=10)
    ai_timeout_seconds: float = Field(30, gt=0, le=120)
    ai_max_concurrent_requests: int = Field(2, ge=1, le=4)
    ai_requests_per_minute: int = Field(6, ge=1, le=60)
    # Standard short-context pricing, verified 2026-10-19. Conservative input estimate
    # includes the documented 1.25x cache-write rate; no cached-input discounts assumed.
    ai_pricing_model: str = 'gpt-5.6-luna'
    ai_input_usd_per_million: Decimal = Field(Decimal('0.25'), gt=0)
    ai_output_usd_per_million: Decimal = Field(Decimal('1.20'), gt=0)
    ai_pricing_verified_on: str = '2026-10-19'
    owner_demo_enabled: bool = True
    ai_session_ttl_seconds: int = Field(1800, ge=60, le=3600)
    ai_budget_scope: str = 'development'
    ai_mode: str = 'OWNER_DEMO'
    ai_configuration_reason: str | None = None
    embedding_model: str = 'text-embedding-3-small'
    embedding_dimensions: int = Field(1536, ge=8, le=1536)
    embedding_version: str = Field('chunks-v1', min_length=1, max_length=40)
    embedding_batch_size: int = Field(16, ge=1, le=32)
    embedding_input_usd_per_million: Decimal = Field(Decimal('.02'), gt=0)
    embedding_pricing_model: str = 'text-embedding-3-small'
    embedding_pricing_verified_on: str = '2026-10-19'
    embedding_batch_quota: int = Field(500, ge=0)
    rag_search_quota: int = Field(200, ge=0)
    rag_question_quota: int = Field(100, ge=0)
    rag_comparison_quota: int = Field(20, ge=0)
    rag_max_documents: int = Field(10, ge=2, le=20)
    rag_max_passages: int = Field(8, ge=2, le=20)
    rag_max_chunks: int = Field(10000, ge=100, le=20000)
    comparison_max_chars: int = Field(200000, ge=1000, le=1000000)
    comparison_max_blocks: int = Field(2000, ge=10, le=5000)
    long_summary_max_parts: int = Field(128, ge=2, le=256)
    long_summary_max_calls: int = Field(255, ge=1, le=511)
    long_summary_overlap_chars: int = Field(200, ge=0, le=500)
    ai_model_context_tokens: int = Field(128000, ge=4096, le=250000)

    @model_validator(mode="after")
    def validate_keys(self):
        if any(len(key) < 32 for key in self.api_keys):
            raise ValueError("Chaque clé API doit contenir au moins 32 caractères")
        return self
