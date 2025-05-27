import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Any

import requests
import vosk
from openai import OpenAI
from pydub import AudioSegment

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class MeetingAnalysis:
    """Структура для анализа технического совещания"""
    transcript: str
    summary: str
    tasks: List[Dict[str, Any]]
    hypotheses: List[Dict[str, str]]
    decisions: List[str]
    participants: List[str]
    technical_areas: List[str]


class TechnicalMeetingSecretary:
    """Цифровой секретарь для автоматизации обработки технических совещаний"""

    def __init__(self,
                 vosk_model_path: str,
                 openai_api_key: str,
                 jira_url: str = None,
                 jira_email: str = None,
                 jira_api_token: str = None):
        """
        Инициализация цифрового секретаря

        Args:
            vosk_model_path: Путь к модели Vosk
            openai_api_key: API ключ OpenAI
            jira_url: URL Jira instance
            jira_email: Email для Jira
            jira_api_token: API токен Jira
        """
        # Настройка Vosk
        self.vosk_model = vosk.Model(vosk_model_path)
        self.vosk_rec = vosk.KaldiRecognizer(self.vosk_model, 16000)
        self.vosk_rec.SetWords(True)

        # Настройка OpenAI
        self.openai_client = OpenAI(api_key=openai_api_key)

        # Настройка Jira (опционально)
        self.jira_url = jira_url
        self.jira_email = jira_email
        self.jira_api_token = jira_api_token

        # Размер чанка для обработки аудио (в миллисекундах)
        self.chunk_size = 45000  # 45 секунд

        # Определение schema для tool calling
        self.meeting_analysis_tool = {
            "type": "function",
            "function": {
                "name": "analyze_technical_meeting",
                "description": "Анализирует транскрипцию технического совещания и извлекает структурированную информацию",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "summary": {
                            "type": "string",
                            "description": "Краткое резюме совещания в 2-3 предложениях"
                        },
                        "tasks": {
                            "type": "array",
                            "description": "Список выявленных задач",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "title": {
                                        "type": "string",
                                        "description": "Название задачи"
                                    },
                                    "description": {
                                        "type": "string",
                                        "description": "Подробное описание задачи"
                                    },
                                    "assignee": {
                                        "type": "string",
                                        "description": "Ответственный за выполнение (если указан)"
                                    },
                                    "priority": {
                                        "type": "string",
                                        "enum": ["высокий", "средний", "низкий"],
                                        "description": "Приоритет задачи"
                                    },
                                    "deadline": {
                                        "type": "string",
                                        "description": "Срок выполнения (если указан)"
                                    },
                                    "technical_area": {
                                        "type": "string",
                                        "enum": ["программирование", "радиоэлектроника", "конструирование",
                                                 "летные испытания", "общее"],
                                        "description": "Техническая область задачи"
                                    }
                                },
                                "required": ["title", "description", "priority", "technical_area"]
                            }
                        },
                        "hypotheses": {
                            "type": "array",
                            "description": "Список гипотез, требующих проверки",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "hypothesis": {
                                        "type": "string",
                                        "description": "Описание гипотезы"
                                    },
                                    "status": {
                                        "type": "string",
                                        "enum": ["требует проверки", "принята", "отклонена"],
                                        "description": "Статус гипотезы"
                                    },
                                    "related_area": {
                                        "type": "string",
                                        "description": "Связанная техническая область"
                                    }
                                },
                                "required": ["hypothesis", "status"]
                            }
                        },
                        "decisions": {
                            "type": "array",
                            "description": "Список принятых решений",
                            "items": {
                                "type": "string",
                                "description": "Описание принятого решения"
                            }
                        },
                        "participants": {
                            "type": "array",
                            "description": "Список участников совещания",
                            "items": {
                                "type": "string",
                                "description": "Имя или роль участника"
                            }
                        },
                        "technical_areas": {
                            "type": "array",
                            "description": "Затронутые технические области",
                            "items": {
                                "type": "string",
                                "enum": ["программирование", "радиоэлектроника", "конструирование", "летные испытания"],
                                "description": "Техническая область"
                            }
                        }
                    },
                    "required": ["summary", "tasks", "hypotheses", "decisions", "participants", "technical_areas"]
                }
            }
        }

    def load_and_preprocess_audio(self, audio_path: str) -> AudioSegment:
        """
        Загрузка и предобработка аудиофайла

        Args:
            audio_path: Путь к аудиофайлу

        Returns:
            AudioSegment: Обработанный аудио
        """
        logger.info(f"Загрузка аудиофайла: {audio_path}")

        # Загрузка аудио с поддержкой различных форматов
        audio = AudioSegment.from_file(audio_path)

        # Конвертация в нужный формат для Vosk (16kHz, mono, WAV)
        audio = audio.set_frame_rate(16000).set_channels(1)

        logger.info(f"Аудио обработано: {len(audio) / 1000:.2f} секунд")
        return audio

    def transcribe_audio_with_vosk(self, audio: AudioSegment) -> str:
        """
        Транскрипция аудио с использованием Vosk

        Args:
            audio: AudioSegment для транскрипции

        Returns:
            str: Текст транскрипции
        """
        logger.info("Начало транскрипции с Vosk...")

        transcript_parts = []
        total_chunks = len(audio) // self.chunk_size + (1 if len(audio) % self.chunk_size else 0)

        # Обработка аудио по чанкам
        for i in range(0, len(audio), self.chunk_size):
            chunk_num = i // self.chunk_size + 1
            logger.info(f"Обработка чанка {chunk_num}/{total_chunks}")

            # Извлечение чанка
            chunk = audio[i:i + self.chunk_size]

            # Конвертация в bytes для Vosk
            chunk_bytes = chunk.raw_data

            # Транскрипция чанка
            if self.vosk_rec.AcceptWaveform(chunk_bytes):
                result = json.loads(self.vosk_rec.Result())
                if result.get('text'):
                    transcript_parts.append(result['text'])

        # Получение финального результата
        final_result = json.loads(self.vosk_rec.FinalResult())
        if final_result.get('text'):
            transcript_parts.append(final_result['text'])

        # Сброс распознавателя для следующего использования
        self.vosk_rec = vosk.KaldiRecognizer(self.vosk_model, 16000)
        self.vosk_rec.SetWords(True)

        full_transcript = ' '.join(transcript_parts)
        logger.info(f"Транскрипция завершена. Длина текста: {len(full_transcript)} символов")

        return full_transcript

    def analyze_meeting_with_openai(self, transcript: str) -> MeetingAnalysis:
        """
        Анализ транскрипции совещания с помощью OpenAI tool calling

        Args:
            transcript: Текст транскрипции

        Returns:
            MeetingAnalysis: Структурированный анализ совещания
        """
        logger.info("Анализ совещания с OpenAI tool calling...")

        # Промпт для анализа технического совещания
        analysis_prompt = f"""
        Проанализируй транскрипцию технического совещания на предприятии, где обсуждались полеты, логи, радиоэлектроника и конструкторские решения.

        Извлеки и структурируй следующую информацию:
        - Краткое резюме совещания
        - Все выявленные задачи с приоритетами и техническими областями
        - Гипотезы, требующие проверки или отработки
        - Принятые решения
        - Участников совещания
        - Затронутые технические области

        Транскрипция совещания:
        {transcript}
        """

        try:
            response = self.openai_client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {
                        "role": "system",
                        "content": "Ты эксперт по анализу технических совещаний на предприятиях. Ты специализируешься на выделении задач, гипотез и решений из технических дискуссий инженеров разных специальностей."
                    },
                    {
                        "role": "user",
                        "content": analysis_prompt
                    }
                ],
                tools=[self.meeting_analysis_tool],
                tool_choice={"type": "function", "function": {"name": "analyze_technical_meeting"}},
                temperature=0.3
            )

            # Извлечение результата из tool call[1][2][5]
            tool_call = response.choices[0].message.tool_calls[0]
            analysis_data = json.loads(tool_call.function.arguments)

            logger.info("Анализ OpenAI завершен с использованием tool calling")

            return MeetingAnalysis(
                transcript=transcript,
                summary=analysis_data.get("summary", ""),
                tasks=analysis_data.get("tasks", []),
                hypotheses=analysis_data.get("hypotheses", []),
                decisions=analysis_data.get("decisions", []),
                participants=analysis_data.get("participants", []),
                technical_areas=analysis_data.get("technical_areas", [])
            )

        except Exception as e:
            logger.error(f"Ошибка при анализе с OpenAI tool calling: {e}")
            # Возвращаем базовую структуру в случае ошибки
            return MeetingAnalysis(
                transcript=transcript,
                summary="Ошибка при создании резюме",
                tasks=[],
                hypotheses=[],
                decisions=[],
                participants=[],
                technical_areas=[]
            )

    def create_jira_payload(self, analysis: MeetingAnalysis, project_key: str) -> Dict[str, Any]:
        """
        Создание payload для Jira API

        Args:
            analysis: Анализ совещания
            project_key: Ключ проекта Jira

        Returns:
            Dict: Payload для создания issue в Jira
        """
        logger.info("Создание payload для Jira...")

        # Форматирование описания для Jira
        description = f"""
        h2. Резюме совещания
        {analysis.summary}

        h2. Участники
        {', '.join(analysis.participants) if analysis.participants else 'Не определены'}

        h2. Технические области
        {', '.join(analysis.technical_areas) if analysis.technical_areas else 'Не определены'}

        h2. Принятые решения
        {chr(10).join([f'* {decision}' for decision in analysis.decisions]) if analysis.decisions else 'Решения не выделены'}

        h2. Гипотезы для проверки
        {chr(10).join([f'* {hyp["hypothesis"]} - {hyp.get("status", "требует проверки")} ({hyp.get("related_area", "")})' for hyp in analysis.hypotheses]) if analysis.hypotheses else 'Гипотезы не выделены'}

        h2. Полная транскрипция
        {analysis.transcript[:500]}{'...' if len(analysis.transcript) > 500 else ''}
        """

        # Основной payload для родительской задачи
        jira_payload = {
            "fields": {
                "project": {
                    "key": project_key
                },
                "summary": f"Техническое совещание - {datetime.now().strftime('%d.%m.%Y %H:%M')}",
                "description": description,
                "issuetype": {
                    "name": "Task"
                },
                "priority": {
                    "name": "Medium"
                },
                "labels": ["техническое-совещание", "автоматический-анализ", "tool-calling"]
            }
        }

        # Добавление подзадач
        subtasks = []
        for i, task in enumerate(analysis.tasks):
            subtask = {
                "fields": {
                    "project": {
                        "key": project_key
                    },
                    "summary": task.get("title", f"Задача {i + 1}"),
                    "description": f"{task.get('description', 'Описание не предоставлено')}\n\nСрок: {task.get('deadline', 'Не указан')}",
                    "issuetype": {
                        "name": "Sub-task"
                    },
                    "priority": {
                        "name": self._map_priority(task.get("priority", "средний"))
                    }
                }
            }

            # Добавление ответственного, если указан
            if task.get("assignee"):
                subtask["fields"]["assignee"] = {"name": task["assignee"]}

            # Добавление метки технической области
            if task.get("technical_area"):
                subtask["fields"]["labels"] = [task["technical_area"].replace(" ", "-")]

            subtasks.append(subtask)

        return {
            "main_task": jira_payload,
            "subtasks": subtasks,
            "metadata": {
                "meeting_date": datetime.now().isoformat(),
                "participants_count": len(analysis.participants),
                "tasks_count": len(analysis.tasks),
                "hypotheses_count": len(analysis.hypotheses),
                "decisions_count": len(analysis.decisions),
                "analysis_method": "openai_tool_calling"
            }
        }

    def _map_priority(self, priority: str) -> str:
        """Маппинг приоритетов для Jira"""
        priority_map = {
            "высокий": "High",
            "средний": "Medium",
            "низкий": "Low"
        }
        return priority_map.get(priority.lower(), "Medium")

    def send_to_jira(self, jira_payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Отправка данных в Jira

        Args:
            jira_payload: Данные для отправки

        Returns:
            Dict: Результат отправки
        """
        if not all([self.jira_url, self.jira_email, self.jira_api_token]):
            logger.warning("Данные Jira не настроены, пропускаем отправку")
            return {"status": "skipped", "reason": "jira_not_configured"}

        logger.info("Отправка данных в Jira...")

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json"
        }

        auth = (self.jira_email, self.jira_api_token)

        try:
            # Создание основной задачи
            main_response = requests.post(
                f"{self.jira_url}/rest/api/3/issue",
                json=jira_payload["main_task"],
                headers=headers,
                auth=auth
            )

            if main_response.status_code == 201:
                main_issue_key = main_response.json()["key"]
                logger.info(f"Основная задача создана: {main_issue_key}")

                # Создание подзадач
                subtask_keys = []
                for subtask in jira_payload["subtasks"]:
                    subtask["fields"]["parent"] = {"key": main_issue_key}

                    subtask_response = requests.post(
                        f"{self.jira_url}/rest/api/3/issue",
                        json=subtask,
                        headers=headers,
                        auth=auth
                    )

                    if subtask_response.status_code == 201:
                        subtask_key = subtask_response.json()["key"]
                        subtask_keys.append(subtask_key)
                        logger.info(f"Подзадача создана: {subtask_key}")

                return {
                    "status": "success",
                    "main_issue": main_issue_key,
                    "subtasks": subtask_keys,
                    "metadata": jira_payload["metadata"]
                }
            else:
                logger.error(f"Ошибка создания основной задачи: {main_response.text}")
                return {
                    "status": "error",
                    "message": main_response.text
                }

        except Exception as e:
            logger.error(f"Ошибка при отправке в Jira: {e}")
            return {
                "status": "error",
                "message": str(e)
            }

    def process_meeting_audio(self,
                              audio_path: str,
                              project_key: str = "MEET",
                              save_json: bool = True,
                              output_path: str = None) -> Dict[str, Any]:
        """
        Полный пайплайн обработки аудио совещания

        Args:
            audio_path: Путь к аудиофайлу
            project_key: Ключ проекта Jira
            save_json: Сохранить результат в JSON файл
            output_path: Путь для сохранения JSON

        Returns:
            Dict: Полный результат обработки
        """
        logger.info("=== НАЧАЛО ОБРАБОТКИ ТЕХНИЧЕСКОГО СОВЕЩАНИЯ ===")

        try:
            # 1. Загрузка и предобработка аудио
            audio = self.load_and_preprocess_audio(audio_path)

            # 2. Транскрипция с Vosk
            transcript = self.transcribe_audio_with_vosk(audio)

            # 3. Анализ с OpenAI tool calling
            analysis = self.analyze_meeting_with_openai(transcript)

            # 4. Создание payload для Jira
            jira_payload = self.create_jira_payload(analysis, project_key)

            # 5. Отправка в Jira (опционально)
            jira_result = self.send_to_jira(jira_payload)

            # 6. Формирование финального результата
            result = {
                "processing_info": {
                    "audio_file": audio_path,
                    "audio_duration_seconds": len(audio) / 1000,
                    "processing_timestamp": datetime.now().isoformat(),
                    "transcript_length": len(transcript),
                    "analysis_method": "openai_tool_calling"
                },
                "analysis": {
                    "summary": analysis.summary,
                    "tasks": analysis.tasks,
                    "hypotheses": analysis.hypotheses,
                    "decisions": analysis.decisions,
                    "participants": analysis.participants,
                    "technical_areas": analysis.technical_areas
                },
                "jira_integration": jira_result,
                "jira_payload": jira_payload,
                "full_transcript": transcript
            }

            # 7. Сохранение в JSON файл
            if save_json:
                if not output_path:
                    output_path = f"meeting_analysis_toolcalling_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

                with open(output_path, 'w', encoding='utf-8') as f:
                    json.dump(result, f, ensure_ascii=False, indent=2)

                logger.info(f"Результат сохранен в: {output_path}")

            logger.info("=== ОБРАБОТКА ЗАВЕРШЕНА УСПЕШНО ===")
            return result

        except Exception as e:
            logger.error(f"Ошибка в процессе обработки: {e}")
            error_result = {
                "status": "error",
                "message": str(e),
                "processing_info": {
                    "audio_file": audio_path,
                    "processing_timestamp": datetime.now().isoformat(),
                    "analysis_method": "openai_tool_calling"
                }
            }

            if save_json:
                error_path = f"meeting_error_toolcalling_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                with open(error_path, 'w', encoding='utf-8') as f:
                    json.dump(error_result, f, ensure_ascii=False, indent=2)
                logger.info(f"Ошибка сохранена в: {error_path}")

            return error_result


# Пример использования
def main():
    """Пример использования цифрового секретаря с tool calling"""

    # Настройки (заменить на свои)
    CONFIG = {
        "vosk_model_path": "path/to/vosk-model-ru-0.42",  # Скачать с https://alphacephei.com/vosk/models
        "openai_api_key": "your-openai-api-key",
        "jira_url": "https://your-domain.atlassian.net",  # Опционально
        "jira_email": "your-email@company.com",  # Опционально
        "jira_api_token": "your-jira-api-token",  # Опционально
        "audio_file": "meeting_recording.wav",  # Путь к аудиофайлу
        "project_key": "TECH"  # Ключ проекта в Jira
    }

    # Создание экземпляра секретаря
    secretary = TechnicalMeetingSecretary(
        vosk_model_path=CONFIG["vosk_model_path"],
        openai_api_key=CONFIG["openai_api_key"],
        jira_url=CONFIG.get("jira_url"),
        jira_email=CONFIG.get("jira_email"),
        jira_api_token=CONFIG.get("jira_api_token")
    )

    # Обработка совещания
    result = secretary.process_meeting_audio(
        audio_path=CONFIG["audio_file"],
        project_key=CONFIG["project_key"],
        save_json=True
    )

    # Вывод краткой сводки
    if result.get("analysis"):
        print("\n=== КРАТКАЯ СВОДКА СОВЕЩАНИЯ (Tool Calling) ===")
        print(f"Резюме: {result['analysis']['summary']}")
        print(f"Количество задач: {len(result['analysis']['tasks'])}")
        print(f"Количество гипотез: {len(result['analysis']['hypotheses'])}")
        print(f"Количество решений: {len(result['analysis']['decisions'])}")

        if result['analysis']['tasks']:
            print("\nВыявленные задачи:")
            for i, task in enumerate(result['analysis']['tasks'], 1):
                print(
                    f"{i}. {task.get('title', 'Без названия')} ({task.get('priority', 'средний')} приоритет, {task.get('technical_area', 'общее')})")

        if result['analysis']['hypotheses']:
            print("\nГипотезы:")
            for i, hyp in enumerate(result['analysis']['hypotheses'], 1):
                print(f"{i}. {hyp.get('hypothesis', 'Не указано')} - {hyp.get('status', 'требует проверки')}")

    return result


if __name__ == "__main__":
    # Установка зависимостей:
    # pip install vosk pydub openai requests

    result = main()
