import json
import logging
import vosk
from pydub import AudioSegment
from typing import List
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
            self.recognizer = vosk.KaldiRecognizer(self.model, 16000)
            self.recognizer.SetWords(True)
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

            # Конвертация в нужный формат для Vosk (16kHz, mono, WAV)
            audio = audio.set_frame_rate(16000).set_channels(1)

            logger.info(f"Аудио обработано: {len(audio) / 1000:.2f} секунд, "
                        f"частота: {audio.frame_rate}Hz, каналы: {audio.channels}")

            return audio

        except Exception as e:
            logger.error(f"Ошибка обработки аудиофайла {audio_path}: {e}")
            raise

    def transcribe_chunk(self, chunk_bytes: bytes) -> str:
        """
        Транскрипция одного чанка аудио

        Args:
            chunk_bytes: Байты аудио чанка

        Returns:
            str: Текст транскрипции чанка
        """
        try:
            if self.recognizer.AcceptWaveform(chunk_bytes):
                result = json.loads(self.recognizer.Result())
                return result.get('text', '')
            return ''
        except Exception as e:
            logger.error(f"Ошибка транскрипции чанка: {e}")
            return ''

    def get_final_result(self) -> str:
        """
        Получение финального результата транскрипции

        Returns:
            str: Финальный текст
        """
        try:
            final_result = json.loads(self.recognizer.FinalResult())
            return final_result.get('text', '')
        except Exception as e:
            logger.error(f"Ошибка получения финального результата: {e}")
            return ''

    def reset_recognizer(self):
        """Сброс распознавателя для новой транскрипции"""
        self.recognizer = vosk.KaldiRecognizer(self.model, 16000)
        self.recognizer.SetWords(True)

    def transcribe_audio(self, audio: AudioSegment) -> str:
        """
        Полная транскрипция аудио

        Args:
            audio: AudioSegment для транскрипции

        Returns:
            str: Полный текст транскрипции
        """
        logger.info("Начало транскрипции аудио...")

        transcript_parts = []
        total_chunks = len(audio) // self.config.chunk_size + (1 if len(audio) % self.config.chunk_size else 0)

        try:
            # Обработка аудио по чанкам
            for i in range(0, len(audio), self.config.chunk_size):
                chunk_num = i // self.config.chunk_size + 1
                logger.info(f"Обработка чанка {chunk_num}/{total_chunks}")

                # Извлечение чанка
                chunk = audio[i:i + self.config.chunk_size]
                chunk_bytes = chunk.raw_data

                # Транскрипция чанка
                chunk_text = self.transcribe_chunk(chunk_bytes)
                if chunk_text:
                    transcript_parts.append(chunk_text)

            # Получение финального результата
            final_text = self.get_final_result()
            if final_text:
                transcript_parts.append(final_text)

            # Сброс распознавателя
            self.reset_recognizer()

            full_transcript = ' '.join(transcript_parts)
            logger.info(f"Транскрипция завершена. Длина текста: {len(full_transcript)} символов")

            return full_transcript

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
