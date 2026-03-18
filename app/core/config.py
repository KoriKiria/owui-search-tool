from functools import lru_cache

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.search_engines import normalize_search_engine
from app.core.search_language import normalize_search_language


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_host: str = "0.0.0.0"
    app_port: int = 8100
    log_level: str = "INFO"
    auth_enabled: bool = False
    api_bearer_token: str | None = None
    cors_allow_origins: list[str] | str = Field(default="*")
    search_max_results: int = Field(default=8, ge=1, le=20)
    search_engine_default: str = "auto"
    search_language_default: str = "auto"
    search_timeout_ms: int = Field(default=20000, ge=500, le=120000)
    fetch_timeout_ms: int = Field(default=8000, ge=100, le=60000)
    fetch_max_concurrency: int = Field(default=4, ge=1, le=20)
    fetch_max_response_bytes: int = Field(default=500000, ge=1024, le=5_000_000)
    fetch_max_pages: int = Field(default=8, ge=1, le=20)
    extract_max_chars: int = Field(default=4000, ge=100, le=50000)
    block_private_networks: bool = True
    browser_enabled: bool = True
    browser_headless: bool = True
    browser_timeout_ms: int = Field(default=12000, ge=100, le=60000)
    browser_locale: str = "en-US"
    browser_user_agent: str = (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
    )
    http_proxy: str | None = Field(default=None, validation_alias=AliasChoices("HTTP_PROXY", "http_proxy"))
    https_proxy: str | None = Field(default=None, validation_alias=AliasChoices("HTTPS_PROXY", "https_proxy"))
    no_proxy: str | None = Field(default=None, validation_alias=AliasChoices("NO_PROXY", "no_proxy"))
    bing_api_key: str | None = Field(default=None, validation_alias=AliasChoices("BING_API_KEY", "bing_api_key"))
    bing_api_endpoint: str | None = Field(
        default=None,
        validation_alias=AliasChoices("BING_API_ENDPOINT", "bing_api_endpoint"),
    )
    brave_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("BRAVE_API_KEY", "brave_api_key"),
    )
    brave_api_endpoint: str | None = Field(
        default=None,
        validation_alias=AliasChoices("BRAVE_API_ENDPOINT", "brave_api_endpoint"),
    )
    google_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("GOOGLE_API_KEY", "google_api_key"),
    )
    google_api_endpoint: str | None = Field(
        default=None,
        validation_alias=AliasChoices("GOOGLE_API_ENDPOINT", "google_api_endpoint"),
    )
    google_cse_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("GOOGLE_CSE_ID", "google_cse_id"),
    )
    duckduckgo_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("DUCKDUCKGO_API_KEY", "duckduckgo_api_key"),
    )
    duckduckgo_api_endpoint: str | None = Field(
        default=None,
        validation_alias=AliasChoices("DUCKDUCKGO_API_ENDPOINT", "duckduckgo_api_endpoint"),
    )

    @field_validator("cors_allow_origins", mode="before")
    @classmethod
    def parse_origins(cls, value: object) -> object:
        if isinstance(value, str) and value != "*":
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("search_engine_default")
    @classmethod
    def validate_search_engine_default(cls, value: str) -> str:
        return normalize_search_engine(value)

    @field_validator("search_language_default")
    @classmethod
    def validate_search_language_default(cls, value: str) -> str:
        return normalize_search_language(value)

    def has_provider_api_key(self, engine: str) -> bool:
        normalized = normalize_search_engine(engine)
        return bool(self.provider_api_credentials(normalized)["api_key"])

    def provider_api_credentials(self, engine: str) -> dict[str, str | None]:
        normalized = normalize_search_engine(engine)
        if normalized == "bing":
            return {
                "api_key": self.bing_api_key,
                "api_endpoint": self.bing_api_endpoint,
                "custom_search_id": None,
            }
        if normalized == "brave":
            return {
                "api_key": self.brave_api_key,
                "api_endpoint": self.brave_api_endpoint,
                "custom_search_id": None,
            }
        if normalized == "google":
            return {
                "api_key": self.google_api_key,
                "api_endpoint": self.google_api_endpoint,
                "custom_search_id": self.google_cse_id,
            }
        if normalized == "duckduckgo":
            return {
                "api_key": self.duckduckgo_api_key,
                "api_endpoint": self.duckduckgo_api_endpoint,
                "custom_search_id": None,
            }
        return {
            "api_key": None,
            "api_endpoint": None,
            "custom_search_id": None,
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
