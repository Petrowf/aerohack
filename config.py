import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class VoskConfig:
    """Конфигурация для Vosk"""
    model_path: str
    chunk_size: int = 45000  # 45 секунд


@dataclass
class OpenAIConfig:
    """Конфигурация для OpenAI"""
    api_key: str
    model: str = "gpt-4"
    temperature: float = 0.3


@dataclass
class WeeekConfig:
    """Конфигурация для Weeek"""
    api_token: str
    workspace_id: str
    project_id: Optional[str] = None
    base_url: str = "https://api.weeek.net/public/v1"


@dataclass
class MeetingSecretaryConfig:
    """Общая конфигурация"""
    vosk: VoskConfig
    openai: OpenAIConfig
    weeek: Optional[WeeekConfig] = None

    @classmethod
    def from_env(cls):
        """Создание конфигурации из переменных окружения"""
        vosk_config = VoskConfig(
            model_path=os.getenv("VOSK_MODEL_PATH", "path/to/vosk-model-ru-0.42")
        )

        openai_config = OpenAIConfig(
            api_key=os.getenv("OPENAI_API_KEY", "")
        )

        weeek_config = None
        if all([os.getenv("WEEEK_API_TOKEN"), os.getenv("WEEEK_WORKSPACE_ID")]):
            weeek_config = WeeekConfig(
                api_token=os.getenv("WEEEK_API_TOKEN"),
                workspace_id=os.getenv("WEEEK_WORKSPACE_ID"),
                project_id=os.getenv("WEEEK_PROJECT_ID")
            )

        return cls(
            vosk=vosk_config,
            openai=openai_config,
            weeek=weeek_config
        )
