from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")
    litellm_api_base: str = ""
    litellm_api_key: str = ""
    request_timeout: float = 180
    database_path: Path = ROOT / "runs.db"
    recordings_path: Path = ROOT / "fixtures/recorded_runs.json"

settings = Settings()
