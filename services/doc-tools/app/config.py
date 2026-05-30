from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    doc_tools_host: str = Field(default="0.0.0.0", alias="DOC_TOOLS_HOST")
    doc_tools_port: int = Field(default=9478, alias="DOC_TOOLS_PORT")
    doc_tools_max_file_mb: int = Field(default=100, alias="DOC_TOOLS_MAX_FILE_MB")
    doc_tools_allowed_roots: str = Field(default="/data/intake", alias="DOC_TOOLS_ALLOWED_ROOTS")
    doc_tools_cache_dir: str = Field(default="/data/cache", alias="DOC_TOOLS_CACHE_DIR")
    doc_tools_log_level: str = Field(default="info", alias="DOC_TOOLS_LOG_LEVEL")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def allowed_roots(self) -> list[Path]:
        return [
            Path(root.strip()).resolve()
            for root in self.doc_tools_allowed_roots.split(",")
            if root.strip()
        ]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
