"""Configuration module for CoolPath AI using Pydantic Settings."""

from typing import List, Tuple
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    """Application configuration settings."""
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Application Meta
    APP_NAME: str = "CoolPath AI"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True
    ENVIRONMENT: str = "development"

    # Server Network
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    CORS_ORIGINS: List[str] = Field(default_factory=lambda: ["*"])

    # FortyGuard API Config
    FORTYGUARD_API_KEY: str = Field(default="", description="FortyGuard Microclimate API Key")
    FORTYGUARD_API_BASE_URL: str = Field(
        default="https://api.fortyguard.com/v1",
        description="FortyGuard API Base Endpoint"
    )
    USE_MOCK_FORTYGUARD: bool = Field(
        default=True,
        description="Toggle fallback deterministic microclimate simulator when API key is missing or offline"
    )

    # Thermal Routing Engine Defaults
    DEFAULT_ALPHA: float = Field(
        default=1.8,
        description="Thermal penalty multiplier alpha: Cost = Distance * (1 + alpha * max(0, Temp - Threshold))"
    )
    DEFAULT_TEMP_THRESHOLD: float = Field(
        default=33.0,
        description="Base heat-stress threshold temperature in Celsius"
    )
    DEFAULT_H3_RESOLUTION: int = Field(
        default=9,
        description="Uber H3 spatial resolution for street-level indexing (8=sub-neighborhood, 9=block/microclimate)"
    )

    # Preset City Scenarios for Demo & Verification
    PRESET_SCENARIOS: dict = Field(
        default_factory=lambda: {
            "phoenix_downtown": {
                "id": "phoenix_downtown",
                "name": "Downtown Phoenix Heat Corridor (USA)",
                "description": "Severe asphalt canyon with 46°C parking lots vs shaded parkway corridors.",
                "center": (33.4484, -112.0740),
                "origin": (33.4445, -112.0805),
                "destination": (33.4545, -112.0650),
                "baseline_ambient_temp": 42.0,
                "zoom": 14
            },
            "dubai_marina": {
                "id": "dubai_marina",
                "name": "Dubai Marina / JBR District (UAE)",
                "description": "High solar radiation asphalt boulevard vs coastal breeze & pedestrian shaded promenade.",
                "center": (25.0805, 55.1403),
                "origin": (25.0710, 55.1320),
                "destination": (25.0920, 55.1510),
                "baseline_ambient_temp": 40.5,
                "zoom": 14
            },
            "austin_east": {
                "id": "austin_east",
                "name": "Austin Eastside Logistics Zone (USA)",
                "description": "Industrial concrete roof heat island vs tree-canopied residential thoroughfares.",
                "center": (30.2672, -97.7431),
                "origin": (30.2580, -97.7550),
                "destination": (30.2780, -97.7280),
                "baseline_ambient_temp": 38.0,
                "zoom": 14
            }
        }
    )


settings = Settings()
