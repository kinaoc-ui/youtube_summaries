from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
TRANSCRIPT_DIR = DATA_DIR / "transcripts"
SUMMARY_DIR = DATA_DIR / "summaries"
OUTPUT_DIR = ROOT / "outputs"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="TUBEON_", extra="ignore")

    # summarizer: offline | ollama | openai | cursor-agent
    llm_provider: str = "offline"
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5:7b"
    openai_base_url: str = "https://api.openai.com/v1"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    chunk_seconds: int = 90
    host: str = "127.0.0.1"
    port: int = 8765
    # ASR fallback when YouTube captions are disabled
    # provider: whisper | whisperx | deepgram
    # A/B sync: python scripts/compare_asr.py <id>  (faster-whisper vs WhisperX)
    # model: small (CPU) | large-v3-turbo (better; GPU recommended)
    asr_provider: str = "whisper"
    whisper_model: str = "small"
    whisper_device: str = "cpu"
    whisper_compute: str = "int8"
    whisper_auto: bool = True
    deepgram_api_key: str = ""
    deepgram_model: str = "nova-3"
    video_max_height: int = 360


settings = Settings()


def ensure_dirs() -> None:
    for d in (DATA_DIR, TRANSCRIPT_DIR, SUMMARY_DIR, OUTPUT_DIR):
        d.mkdir(parents=True, exist_ok=True)
