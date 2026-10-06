"""Environment-driven configuration. Every setting can be set as ``DLC_<NAME>``."""

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/datalake_canvas/config.py -> repo root. Only meaningful for editable/dev
# installs; the Docker image sets DLC_ROOT explicitly.
_DEFAULT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="DLC_", env_file=_DEFAULT_ROOT / ".env", extra="ignore"
    )

    # Paths ---------------------------------------------------------------
    root: Path = _DEFAULT_ROOT
    """Repo root; exposed to datasource config files as ``${DLC_ROOT}``."""
    data_dir: Path | None = None
    """Folder holding demo data; exposed as ``${DLC_DATA_DIR}``. Defaults to examples/demo-data."""
    datasources_file: Path | None = None
    """JSON file describing MCP data sources. Defaults to config/datasources.json."""
    workflows_dir: Path = Path("./data/workflows")

    # Safety --------------------------------------------------------------
    allow_write_queries: bool = False
    """Read-only by default. Setting this lifts the SQL guard (see docs/architecture.md)."""
    max_rows: int = Field(default=1000, ge=1)
    query_timeout_seconds: float = Field(default=30.0, gt=0)

    # HTTP ----------------------------------------------------------------
    cors_origins: str = "http://localhost:5173,http://localhost:8080"
    """Comma-separated list of allowed browser origins."""

    # Agent ---------------------------------------------------------------
    llm_provider: str = "openai"
    openai_model: str = "gpt-4.1-mini"
    # Accepts the conventional OPENAI_API_KEY as well as DLC_OPENAI_API_KEY.
    openai_api_key: str | None = Field(
        default=None, validation_alias=AliasChoices("OPENAI_API_KEY", "DLC_OPENAI_API_KEY")
    )

    @property
    def resolved_data_dir(self) -> Path:
        return self.data_dir or self.root / "examples" / "demo-data"

    @property
    def resolved_datasources_file(self) -> Path:
        return self.datasources_file or self.root / "config" / "datasources.json"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
