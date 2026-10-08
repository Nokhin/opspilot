from datetime import datetime
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import AwareDatetime, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OPSPILOT_", env_file=".env", extra="ignore")
    data_dir: Path = Path("var")
    corpus_dir: Path = Path("corpus/policies")
    reference_time: AwareDatetime = datetime.fromisoformat("2026-10-01T00:00:00+00:00")
    app_env: Literal["development", "demo", "production"] = "demo"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    llm_provider: Literal["extractive", "chat_api"] = "extractive"
    llm_base_url: str = "https://api.groq.com/openai/v1"
    llm_model: str = ""
    llm_api_key: SecretStr = SecretStr("")
    embedding_provider: Literal["tfidf", "embedding_api"] = "tfidf"
    embedding_base_url: str = ""
    embedding_model: str = ""
    embedding_api_key: SecretStr = SecretStr("")
    top_k: int = Field(default=6, ge=1, le=8)
    max_tool_calls: int = Field(default=4, ge=1, le=4)
    provider_timeout_seconds: float = Field(default=20, ge=1, le=60)
    provider_retries: int = Field(default=1, ge=0, le=2)
    input_cost_per_million: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    output_cost_per_million: float | None = Field(default=None, ge=0, allow_inf_nan=False)

    @field_validator("input_cost_per_million", "output_cost_per_million", mode="before")
    @classmethod
    def empty_optional_cost(cls, value):
        return None if value == "" else value

    @field_validator("llm_base_url", "embedding_base_url")
    @classmethod
    def validate_endpoint(cls, value):
        if not value:
            return value
        url = urlsplit(value)
        local_http = url.scheme == "http" and url.hostname in {"localhost", "127.0.0.1", "::1"}
        if not url.netloc or (url.scheme != "https" and not local_http):
            raise ValueError("Provider endpoints require HTTPS or loopback HTTP")
        if url.username or url.password or url.query or url.fragment:
            raise ValueError("Provider endpoint must not embed credentials, query or fragment")
        return value

    @model_validator(mode="after")
    def validate_provider(self):
        if self.llm_provider == "chat_api" and not (
            self.llm_model and self.llm_base_url and self.llm_api_key.get_secret_value()
        ):
            raise ValueError("chat_api requires LLM model, base URL and API key")
        if self.embedding_provider == "embedding_api" and not (
            self.embedding_model
            and self.embedding_base_url
            and self.embedding_api_key.get_secret_value()
        ):
            raise ValueError("embedding_api requires model, base URL and API key")
        return self

    @property
    def incident_db(self) -> Path:
        return self.data_dir / "incidents.sqlite"

    @property
    def vector_index(self) -> Path:
        return self.data_dir / "policy_index.json"
