from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./tripweave.db"
    secret_key: str = "dev-only-change-me-use-a-long-random-value"
    access_token_minutes: int = 60 * 12
    cors_origins: str = "http://localhost:5173"

    # Routing: "none" = honest straight-line estimates only; "osrm" = OSRM-compatible /table API.
    routing_provider: str = "none"
    osrm_base_url: str = ""
    routing_timeout_s: float = 8.0
    routing_max_points: int = 80

    # Currency conversion: "none" keeps currencies separate; "frankfurter" = ECB reference rates.
    fx_provider: str = "none"
    fx_base_url: str = "https://api.frankfurter.dev/v1"
    fx_timeout_s: float = 6.0

    map_tile_url: str = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
    map_tile_attribution: str = (
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
    )

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
