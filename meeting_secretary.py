import json
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
from pathlib import Path

from config import MeetingSecretaryConfig, VoskConfig, OpenAIConfig, WeeekConfig
from vosk_transcriber import VoskTranscriber
from openai_analyzer import OpenAIAnalyzer, MeetingAnalysis
from openai_transcriber import OpenAITranscriber
from weeek_integration import WeeekIntegration

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class TechnicalMeetingSecretary:
    """Главный класс цифрового секретаря для технических совещаний с интеграцией Weeek"""

    def __init__(self, config: MeetingSecretaryConfig):
        """
        Инициализация секретаря

        Args:
            config: Конфигурация секретаря
        """
        self.config = config

        # Инициализация компонентов
        logger.info("Инициализация компонентов цифрового секретаря...")

        # OpenAI транскрибер
        self.transcriber = OpenAITranscriber(config.openai)

        # OpenAI анализатор
        self.analyzer = OpenAIAnalyzer(config.openai)

        self.weeek_integration = WeeekIntegration(config.weeek)

        logger.info("Инициализация завершена")

    def process_meeting_audio(self,
                              audio_path: str,) -> float:
        """
        Полный пайплайн обработки аудио совещания

        Args:
            audio_path: Путь к аудиофайлу
            project_id: ID проекта Weeek (опционально)
            save_json: Сохранить результат в JSON
            output_dir: Директория для сохранения результатов

        Returns:
            Dict: Результат обработки
        """
        logger.info("=== НАЧАЛО ОБРАБОТКИ ТЕХНИЧЕСКОГО СОВЕЩАНИЯ ===")
        start_time = datetime.now()

        try:
            # 1. Транскрипция аудио
            logger.info("Этап 1: Транскрипция аудио")
            transcript = self.transcriber.transcribe_from_file(audio_path)

            if not transcript.strip():
                raise ValueError("Пустая транскрипция - проверьте аудиофайл")

            # 2. Анализ транскрипции
            logger.info("Этап 2: Анализ транскрипции")
            analysis = self.analyzer.analyze_transcript(transcript)

            # Валидация анализа
            if not self.analyzer.validate_analysis(analysis):
                logger.warning("Анализ содержит ошибки, но продолжаем")

            # 3. Интеграция с Weeek
            self.weeek_integration.create_tasks_from_analysis(analysis)


            # 4. Формирование результата
            processing_time = (datetime.now() - start_time).total_seconds()
            logger.info(f"=== ОБРАБОТКА ЗАВЕРШЕНА УСПЕШНО ЗА {processing_time:.2f} СЕКУНД ===")
            return processing_time

        except Exception as e:
            processing_time = (datetime.now() - start_time).total_seconds()
            logger.error(f"Ошибка при обработке: {e}")
            raise ValueError(f"Ошибка анализа")





