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
class JiraConfig:
    """Конфигурация для Jira"""
    url: str
    email: str
    api_token: str
    project_key: str = "MEET"


@dataclass
class MeetingSecretaryConfig:
    """Общая конфигурация"""
    vosk: VoskConfig
    openai: OpenAIConfig
    jira: Optional[JiraConfig] = None

    @classmethod
    def from_env(cls):
        """Создание конфигурации из переменных окружения"""
        vosk_config = VoskConfig(
            model_path=os.getenv("VOSK_MODEL_PATH", "path/to/vosk-model-ru-0.42")
        )

        openai_config = OpenAIConfig(
            api_key=os.getenv("OPENAI_API_KEY", "")
        )

        jira_config = None
        if all([os.getenv("JIRA_URL"), os.getenv("JIRA_EMAIL"), os.getenv("JIRA_API_TOKEN")]):
            jira_config = JiraConfig(
                url=os.getenv("JIRA_URL"),
                email=os.getenv("JIRA_EMAIL"),
                api_token=os.getenv("JIRA_API_TOKEN"),
                project_key=os.getenv("JIRA_PROJECT_KEY", "MEET")
            )

        return cls(
            vosk=vosk_config,
            openai=openai_config,
            jira=jira_config
        )
