import json
import logging

import vosk
from pydub import AudioSegment

from config import VoskConfig

logger = logging.getLogger(__name__)


class VoskTranscriber:
    """Класс для транскрипции аудио с помощью Vosk"""

    def __init__(self, config: VoskConfig):
        """
        Инициализация транскрибера

        Args:
            config: Конфигурация Vosk
        """
        self.config = config
        logger.info(f"Загрузка модели Vosk из: {config.model_path}")

        try:
            self.model = vosk.Model(config.model_path)
            logger.info("Модель Vosk успешно загружена")
        except Exception as e:
            logger.error(f"Ошибка загрузки модели Vosk: {e}")
            raise

    def load_and_preprocess_audio(self, audio_path: str) -> AudioSegment:
        """
        Загрузка и предобработка аудиофайла

        Args:
            audio_path: Путь к аудиофайлу

        Returns:
            AudioSegment: Обработанный аудио
        """
        logger.info(f"Загрузка аудиофайла: {audio_path}")

        try:
            # Загрузка аудио с поддержкой различных форматов
            audio = AudioSegment.from_file(audio_path)

            # Конвертация в нужный формат для Vosk (16kHz, mono, 16-bit PCM)
            audio = audio.set_frame_rate(16000).set_channels(1).set_sample_width(2)

            logger.info(f"Аудио обработано: {len(audio) / 1000:.2f} секунд")

            return audio

        except Exception as e:
            logger.error(f"Ошибка обработки аудиофайла {audio_path}: {e}")
            raise

    def transcribe_audio(self, audio: AudioSegment) -> str:
        """
        Полная транскрипция аудио

        Args:
            audio: AudioSegment для транскрипции

        Returns:
            str: Полный текст транскрипции
        """
        logger.info("Начало транскрипции аудио...")

        try:
            # Создаем новый распознаватель для каждой транскрипции
            recognizer = vosk.KaldiRecognizer(self.model, 16000)
            recognizer.SetWords(True)

            # Передаем все аудио сразу
            raw_data = audio.raw_data
            recognizer.AcceptWaveform(raw_data)

            # Получаем финальный результат
            final_result = json.loads(recognizer.FinalResult())
            transcript = final_result.get('text', '')

            logger.info(f"Транскрипция завершена. Длина текста: {len(transcript)} символов")

            return transcript

        except Exception as e:
            logger.error(f"Ошибка при транскрипции: {e}")
            raise

    def transcribe_from_file(self, audio_path: str) -> str:
        """
        Транскрипция аудио из файла

        Args:
            audio_path: Путь к аудиофайлу

        Returns:
            str: Текст транскрипции
        """
        audio = self.load_and_preprocess_audio(audio_path)
        return self.transcribe_audio(audio)
