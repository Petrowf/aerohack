import json
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
from pathlib import Path

from config import MeetingSecretaryConfig, VoskConfig, OpenAIConfig, WeeekConfig
from vosk_transcriber import VoskTranscriber
from openai_analyzer import OpenAIAnalyzer, MeetingAnalysis
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

        # Vosk транскрибер
        self.transcriber = VoskTranscriber(config.vosk)

        # OpenAI анализатор
        self.analyzer = OpenAIAnalyzer(config.openai)

        # Weeek интеграция (опционально)
        self.weeek_integration = None
        if config.weeek:
            try:
                self.weeek_integration = WeeekIntegration(config.weeek)
                logger.info("Weeek интеграция активирована")
            except Exception as e:
                logger.warning(f"Не удалось инициализировать Weeek интеграцию: {e}")
        else:
            logger.info("Weeek интеграция отключена")

        logger.info("Инициализация завершена")

    def process_meeting_audio(self,
                              audio_path: str,
                              project_id: Optional[str] = None,
                              save_json: bool = True,
                              output_dir: str = "results") -> Dict[str, Any]:
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

        # Создание директории для результатов
        Path(output_dir).mkdir(exist_ok=True)

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
            weeek_result = None
            if self.weeek_integration and analysis.tasks:
                logger.info("Этап 3: Создание задач в Weeek")
                try:
                    weeek_result = self.weeek_integration.create_tasks_from_analysis(
                        analysis, project_id
                    )
                except Exception as e:
                    logger.error(f"Ошибка интеграции с Weeek: {e}")
                    weeek_result = {"status": "error", "message": str(e)}
            else:
                logger.info("Этап 3: Пропуск интеграции с Weeek")
                weeek_result = {"status": "skipped", "reason": "no_tasks_or_disabled"}

            # 4. Формирование результата
            processing_time = (datetime.now() - start_time).total_seconds()

            result = {
                "processing_info": {
                    "audio_file": audio_path,
                    "processing_timestamp": start_time.isoformat(),
                    "processing_time_seconds": processing_time,
                    "transcript_length": len(transcript),
                    "status": "success"
                },
                "analysis": {
                    "summary": analysis.summary,
                    "tasks": analysis.tasks,
                    "hypotheses": analysis.hypotheses,
                    "decisions": analysis.decisions,
                    "participants": analysis.participants,
                    "technical_areas": analysis.technical_areas
                },
                "weeek_integration": weeek_result,
                "full_transcript": transcript,
                "statistics": {
                    "tasks_count": len(analysis.tasks),
                    "hypotheses_count": len(analysis.hypotheses),
                    "decisions_count": len(analysis.decisions),
                    "participants_count": len(analysis.participants),
                    "technical_areas_count": len(analysis.technical_areas)
                }
            }

            # 5. Сохранение результата
            if save_json:
                output_file = self._save_result(result, output_dir)
                result["processing_info"]["output_file"] = output_file

            logger.info(f"=== ОБРАБОТКА ЗАВЕРШЕНА УСПЕШНО ЗА {processing_time:.2f} СЕКУНД ===")
            return result

        except Exception as e:
            processing_time = (datetime.now() - start_time).total_seconds()
            logger.error(f"Ошибка при обработке: {e}")

            error_result = {
                "processing_info": {
                    "audio_file": audio_path,
                    "processing_timestamp": start_time.isoformat(),
                    "processing_time_seconds": processing_time,
                    "status": "error",
                    "error_message": str(e)
                },
                "analysis": None,
                "weeek_integration": None,
                "full_transcript": None
            }

            if save_json:
                error_file = self._save_result(error_result, output_dir, is_error=True)
                error_result["processing_info"]["error_file"] = error_file

            return error_result

    def _save_result(self, result: Dict[str, Any], output_dir: str, is_error: bool = False) -> str:
        """
        Сохранение результата в JSON файл

        Args:
            result: Результат для сохранения
            output_dir: Директория для сохранения
            is_error: Флаг ошибки

        Returns:
            str: Путь к сохраненному файлу
        """
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        prefix = "error" if is_error else "meeting_analysis"
        filename = f"{prefix}_{timestamp}.json"
        filepath = Path(output_dir) / filename

        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)

            logger.info(f"Результат сохранен: {filepath}")
            return str(filepath)

        except Exception as e:
            logger.error(f"Ошибка сохранения файла: {e}")
            return ""

    def print_analysis_summary(self, result: Dict[str, Any]):
        """
        Вывод краткой сводки анализа

        Args:
            result: Результат анализа
        """
        if result.get("processing_info", {}).get("status") != "success":
            print(f"❌ Ошибка обработки: {result.get('processing_info', {}).get('error_message')}")
            return

        analysis = result.get("analysis", {})
        stats = result.get("statistics", {})
        weeek = result.get("weeek_integration", {})

        print("\n" + "=" * 60)
        print("📋 КРАТКАЯ СВОДКА ТЕХНИЧЕСКОГО СОВЕЩАНИЯ")
        print("=" * 60)

        print(f"\n📝 Резюме:")
        print(f"   {analysis.get('summary', 'Не создано')}")

        print(f"\n📊 Статистика:")
        print(f"   • Задач выявлено: {stats.get('tasks_count', 0)}")
        print(f"   • Решений принято: {stats.get('decisions_count', 0)}")
        print(f"   • Гипотез для проверки: {stats.get('hypotheses_count', 0)}")
        print(f"   • Участников: {stats.get('participants_count', 0)}")

        if analysis.get('tasks'):
            print(f"\n✅ Выявленные задачи:")
            for i, task in enumerate(analysis['tasks'], 1):
                print(f"   {i}. {task.get('название', 'Без названия')}")
                print(f"      ➤ Исполнитель: {task.get('кто_выполняет', 'Не назначен')}")
                print(f"      ➤ Срок: {task.get('срок', 'Не указан')}")

        if weeek.get("status") == "success":
            print(f"\n🎯 Weeek интеграция:")
            project = weeek.get('project', {})
            print(f"   • Проект: {project.get('name', 'Не указан')}")
            print(f"   • Задач создано: {weeek.get('stats', {}).get('created_tasks', 0)}")

            if self.weeek_integration and project.get('id'):
                project_url = self.weeek_integration.get_project_url(project['id'])
                print(f"   • Ссылка на проект: {project_url}")

            # Показ созданных задач
            created_tasks = weeek.get('tasks', [])
            if created_tasks:
                print(f"   • Созданные задачи:")
                for task in created_tasks:
                    if task.get('type') == 'task':
                        print(f"     - {task.get('title', 'Без названия')}")
        elif weeek.get("status") == "error":
            print(f"\n❌ Ошибка Weeek интеграции: {weeek.get('message', 'Неизвестная ошибка')}")
        else:
            print(f"\n⚠️  Weeek интеграция пропущена")

        processing_time = result.get("processing_info", {}).get("processing_time_seconds", 0)
        print(f"\n⏱️  Время обработки: {processing_time:.2f} секунд")
        print("=" * 60)

    def get_weeek_workspaces(self) -> List[Dict[str, Any]]:
        """
        Получение списка рабочих пространств Weeek

        Returns:
            List[Dict]: Список рабочих пространств
        """
        if not self.weeek_integration:
            logger.warning("Weeek интеграция не инициализирована")
            return []

        return self.weeek_integration.get_workspaces()

    def get_weeek_projects(self, workspace_id: str = None) -> List[Dict[str, Any]]:
        """
        Получение списка проектов Weeek

        Args:
            workspace_id: ID рабочего пространства

        Returns:
            List[Dict]: Список проектов
        """
        if not self.weeek_integration:
            logger.warning("Weeek интеграция не инициализирована")
            return []

        return self.weeek_integration.get_projects(workspace_id)


def main():
    """Пример использования цифрового секретаря с Weeek"""

    # Создание конфигурации
    config = MeetingSecretaryConfig(
        vosk=VoskConfig(
            model_path="path/to/vosk-model-ru-0.42"  # Замените на ваш путь
        ),
        openai=OpenAIConfig(
            api_key="your-openai-api-key"  # Замените на ваш ключ
        ),
        weeek=WeeekConfig(  # Опционально
            api_token="your-weeek-api-token",
            workspace_id="your-workspace-id",
            project_id="your-project-id"  # Опционально
        )
    )

    # Можно также использовать конфигурацию из переменных окружения
    # config = MeetingSecretaryConfig.from_env()

    # Создание секретаря
    secretary = TechnicalMeetingSecretary(config)

    # Показ доступных проектов
    if secretary.weeek_integration:
        print("\n📁 Доступные проекты в Weeek:")
        projects = secretary.get_weeek_projects()
        for project in projects[:5]:  # Показываем первые 5
            print(f"   • {project.get('name')} (ID: {project.get('id')})")

    # Обработка совещания
    audio_file = "meeting_recording.wav"  # Замените на ваш файл

    try:
        result = secretary.process_meeting_audio(
            audio_path=audio_file,
            project_id=None,  # Будет создан новый проект
            save_json=True,
            output_dir="meeting_results"
        )

        # Вывод сводки
        secretary.print_analysis_summary(result)

        return result

    except FileNotFoundError:
        logger.error(f"Аудиофайл не найден: {audio_file}")
    except Exception as e:
        logger.error(f"Неожиданная ошибка: {e}")


if __name__ == "__main__":
    result = main()
