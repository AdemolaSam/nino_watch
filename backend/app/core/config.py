from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "NiñoWatch"
    database_url: str = "postgresql+asyncpg://nino:nino@localhost:5432/nino"
    redis_url: str = "redis://localhost:6379/0"
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000"]
    )
    admin_token: str = ""
    daily_llm_budget_usd: float = 10.0
    model_api_key: str = ""
    model_base_url: str = "https://api.meta.ai/v1"
    openweights_base_url: str = ""
    openweights_api_key: str = ""
    llm_extract: str = "meta:muse-spark-1.3"
    llm_verify_signal: str = "meta:muse-spark-1.3"
    llm_advisory: str = "meta:muse-spark-1.3"
    llm_translate: str = "meta:muse-spark-1.3"
    llm_outlet: str = ""

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_origins(cls, v: object) -> object:
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @property
    def cors_origins_list(self) -> list[str]:
        return self.cors_origins


settings = Settings()
