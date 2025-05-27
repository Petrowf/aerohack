import logging
from typing import Optional

import dotenv
# Импортируем OpenAI клиент
from openai import OpenAI, APIStatusError, AuthenticationError, OpenAIError
dotenv.load_dotenv()
logger = logging.getLogger(__name__)

# Если вы хотите избежать создания config.py, можете просто определить класс OpenAIConfig здесь:
import os
from dataclasses import dataclass


@dataclass
class OpenAIConfig:
    """Конфигурация для OpenAI API"""
    api_key: str = os.getenv("OPENAI_API_KEY")  # Предполагаем, что ключ берется из переменных окружения
    model_name: str = "gpt-4o-mini-transcribe"  # Модель по умолчанию для транскрипции

    def __post_init__(self):
        if not self.api_key:
            raise ValueError(
                "OPENAI_API_KEY не установлен. Пожалуйста, установите переменную окружения или передайте ключ.")


class OpenAITranscriber:
    """Класс для транскрипции аудио с помощью OpenAI Whisper API"""

    def __init__(self, config: OpenAIConfig):
        """
        Инициализация транскрибера

        Args:
            config: Конфигурация OpenAI
        """
        self.config = config
        logger.info(f"Инициализация OpenAI транскрибера с моделью: {config.model_name}")

        try:
            self.client = OpenAI(api_key=config.api_key)
            logger.info("OpenAI клиент успешно инициализирован")
        except AuthenticationError as e:
            logger.error(f"Ошибка аутентификации OpenAI API: {e}")
            raise
        except OpenAIError as e:
            logger.error(f"Общая ошибка инициализации OpenAI клиента: {e}")
            raise

    def transcribe_from_file(self, audio_path: str, model_name: Optional[str] = None) -> str:
        """
        Транскрипция аудио из файла с использованием OpenAI Whisper API

        Args:
            audio_path: Путь к аудиофайлу (поддерживаются mp3, mp4, m4a, wav, flac, aac, ogg)
            model_name: (Опционально) Имя модели Whisper для использования (например, "whisper-1").
                        Если не указано, используется модель из конфигурации.

        Returns:
            str: Текст транскрипции
        """
        logger.info(f"Начало транскрипции аудиофайла: {audio_path} с OpenAI Whisper")

        chosen_model = model_name if model_name else self.config.model_name

        try:
            with open(audio_path, "rb") as audio_file:
                # Вызов API для транскрипции
                transcription = self.client.audio.transcriptions.create(
                    model=chosen_model,
                    file=audio_file,
                    response_format="text",
                    prompt="Представлено совещание о сроках выполнения, задачах и выполняющих в научно-деловом стиле. В данном совещании обрати особое внимание на диалоги между собеседниками, в диалогах указывай, кто говорит, если собеседники представляются."  # Просим вернуть чистый текст
                )

            # OpenAI API возвращает напрямую строку, если response_format="text"
            transcript_text = str(transcription)

            logger.info(f"Транскрипция завершена для {audio_path}. Длина текста: {len(transcript_text)} символов")
            return transcript_text

        except FileNotFoundError:
            logger.error(f"Ошибка: Аудиофайл не найден по пути: {audio_path}")
            raise
        except AuthenticationError as e:
            logger.error(f"Ошибка аутентификации OpenAI API при транскрипции: {e}")
            raise
        except APIStatusError as e:
            logger.error(f"Ошибка статуса OpenAI API при транскрипции (код: {e.status_code}): {e.response}")
            raise
        except OpenAIError as e:
            logger.error(f"Общая ошибка OpenAI при транскрипции: {e}")
            raise
        except Exception as e:
            logger.error(f"Неизвестная ошибка при транскрипции файла {audio_path}: {e}")
            raise