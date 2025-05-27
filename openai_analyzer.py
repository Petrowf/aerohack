import json
import logging
from typing import Dict, List, Any
from dataclasses import dataclass
from openai import OpenAI
from config import OpenAIConfig
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors

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

class OpenAIAnalyzer:
    """Класс для анализа транскрипции с помощью OpenAI"""

    def __init__(self, config: OpenAIConfig):
        """
        Инициализация анализатора

        Args:
            config: Конфигурация OpenAI
        """
        self.config = config
        self.client = OpenAI(api_key=config.api_key)

        # Определение схемы для tool calling
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
                            "description": "Список выявленных задач с полной информацией",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "название": {
                                        "type": "string",
                                        "description": "Название задачи (краткое и емкое)"
                                    },
                                    "описание": {
                                        "type": "string",
                                        "description": "Подробное описание задачи с техническими деталями"
                                    },
                                    "суть_задачи": {
                                        "type": "string",
                                        "description": "Краткая суть задачи в 1-2 предложениях, основная цель"
                                    },
                                    "кто_выполняет": {
                                        "type": "string",
                                        "description": "Ответственный за выполнение (имя, должность или отдел)"
                                    },
                                    "срок": {
                                        "type": "string",
                                        "description": "Срок выполнения в формате YYYY-MM-DD или текстовом виде"
                                    }
                                },
                                "required": ["название", "описание", "суть_задачи", "кто_выполняет", "срок"]
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

    def create_analysis_prompt(self, transcript: str) -> str:
        """
        Создание промпта для анализа

        Args:
            transcript: Текст транскрипции

        Returns:
            str: Промпт для анализа
        """
        return f"""
        Проанализируй транскрипцию технического совещания на предприятии.

        Для каждой задачи обязательно заполни все основные поля:
        - название: краткое название задачи
        - описание: подробное техническое описание
        - суть_задачи: краткая суть в 1-2 предложениях
        - кто_выполняет: конкретный исполнитель (если не указан, то определи по контексту или укажи отдел/роль)
        - срок: конкретная дата или период выполнения (если не указан, предложи разумный срок)

        Обрати особое внимание на:
        - Технические решения и их обоснование
        - Проблемы, которые нужно решить
        - Распределение ответственности между участниками
        - Временные рамки выполнения задач

        Транскрипция совещания:
        {transcript}
        """

    def parse_tool_response(self, response) -> Dict[str, Any]:
        """
        Парсинг ответа от tool calling

        Args:
            response: Ответ от OpenAI

        Returns:
            Dict: Распарсенные данные
        """
        try:
            tool_call = response.choices[0].message.tool_calls[0]
            return json.loads(tool_call.function.arguments)
        except (IndexError, KeyError, json.JSONDecodeError) as e:
            logger.error(f"Ошибка парсинга ответа tool calling: {e}")
            raise

    def analyze_transcript(self, transcript: str) -> MeetingAnalysis:
        """
        Анализ транскрипции совещания

        Args:
            transcript: Текст транскрипции

        Returns:
            MeetingAnalysis: Структурированный анализ
        """
        logger.info("Начало анализа транскрипции с OpenAI...")

        if not transcript.strip():
            logger.warning("Пустая транскрипция для анализа")
            return self._create_empty_analysis(transcript)

        try:
            analysis_prompt = self.create_analysis_prompt(transcript)

            response = self.client.chat.completions.create(
                model=self.config.model,
                messages=[
                    {
                        "role": "system",
                        "content": "Ты эксперт по анализу технических совещаний на предприятиях. "
                                   "Ты специализируешься на выделении задач, гипотез и решений из "
                                   "технических дискуссий инженеров разных специальностей. "
                                   "Для каждой задачи ты ОБЯЗАТЕЛЬНО заполняешь все поля. "
                                   "Если информация не указана явно, пиши о неуказанности."
                                   "Если информация отсутствует, пиши об отсутствии."
                    },
                    {
                        "role": "user",
                        "content": analysis_prompt
                    }
                ],
                tools=[self.meeting_analysis_tool],
                tool_choice={"type": "function", "function": {"name": "analyze_technical_meeting"}},
                temperature=self.config.temperature
            )

            analysis_data = self.parse_tool_response(response)

            logger.info(f"Анализ завершен. Найдено задач: {len(analysis_data.get('tasks', []))}")

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
            logger.error(f"Ошибка при анализе с OpenAI: {e}")
            return self._create_empty_analysis(transcript, str(e))

    def _create_empty_analysis(self, transcript: str, error_message: str = "") -> MeetingAnalysis:
        """
        Создание пустого анализа в случае ошибки

        Args:
            transcript: Исходная транскрипция
            error_message: Сообщение об ошибке

        Returns:
            MeetingAnalysis: Пустой анализ
        """
        summary = f"Ошибка при создании резюме: {error_message}" if error_message else "Анализ не выполнен"

        return MeetingAnalysis(
            transcript=transcript,
            summary=summary,
            tasks=[],
            hypotheses=[],
            decisions=[],
            participants=[],
            technical_areas=[]
        )

    def validate_analysis(self, analysis: MeetingAnalysis) -> bool:
        """
        Валидация результатов анализа

        Args:
            analysis: Анализ для валидации

        Returns:
            bool: True если анализ валиден
        """
        if not analysis.summary:
            logger.warning("Отсутствует резюме совещания")
            return False

        # Проверка структуры задач
        for i, task in enumerate(analysis.tasks):
            required_fields = ["название", "описание", "суть_задачи", "кто_выполняет", "срок"]
            for field in required_fields:
                if not task.get(field):
                    logger.warning(f"Задача {i + 1}: отсутствует поле '{field}'")
                    return False

        logger.info(f"Анализ валиден: {len(analysis.tasks)} задач, {len(analysis.decisions)} решений")
        return True

    def save_analysis_to_pdf(self, analysis: MeetingAnalysis, filename: str) -> None:
        """
        Сохраняет результаты анализа совещания в PDF-файл.

        Args:
            analysis (MeetingAnalysis): Объект с анализом совещания.
            filename (str): Имя файла для сохранения PDF.
        """
        doc = SimpleDocTemplate(filename, pagesize=letter)
        styles = getSampleStyleSheet()
        story = []

        # Заголовок
        story.append(Paragraph("Анализ технического совещания", styles['Title']))
        story.append(Spacer(1, 12))

        # Резюме
        story.append(Paragraph("Резюме:", styles['Heading2']))
        story.append(Paragraph(analysis.summary, styles['BodyText']))
        story.append(Spacer(1, 12))

        # Задачи
        story.append(Paragraph("Задачи:", styles['Heading2']))
        if analysis.tasks:
            data = [["Название", "Описание", "Суть задачи", "Исполнитель", "Срок"]]
            for task in analysis.tasks:
                data.append([
                    task.get("название", ""),
                    task.get("описание", ""),
                    task.get("суть_задачи", ""),
                    task.get("кто_выполняет", ""),
                    task.get("срок", "")
                ])
            table = Table(data)
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))
            story.append(table)
        else:
            story.append(Paragraph("Задачи не найдены.", styles['BodyText']))
        story.append(Spacer(1, 12))

        # Гипотезы
        story.append(Paragraph("Гипотезы:", styles['Heading2']))
        if analysis.hypotheses:
            for hypothesis in analysis.hypotheses:
                story.append(Paragraph(f"- {hypothesis.get('hypothesis', '')} ({hypothesis.get('status', '')})", styles['BodyText']))
        else:
            story.append(Paragraph("Гипотезы не найдены.", styles['BodyText']))
        story.append(Spacer(1, 12))

        # Решения
        story.append(Paragraph("Решения:", styles['Heading2']))
        if analysis.decisions:
            for decision in analysis.decisions:
                story.append(Paragraph(f"- {decision}", styles['BodyText']))
        else:
            story.append(Paragraph("Решения не найдены.", styles['BodyText']))
        story.append(Spacer(1, 12))

        # Участники
        story.append(Paragraph("Участники:", styles['Heading2']))
        if analysis.participants:
            for participant in analysis.participants:
                story.append(Paragraph(f"- {participant}", styles['BodyText']))
        else:
            story.append(Paragraph("Участники не указаны.", styles['BodyText']))
        story.append(Spacer(1, 12))

        # Технические области
        story.append(Paragraph("Технические области:", styles['Heading2']))
        if analysis.technical_areas:
            for area in analysis.technical_areas:
                story.append(Paragraph(f"- {area}", styles['BodyText']))
        else:
            story.append(Paragraph("Технические области не указаны.", styles['BodyText']))

        # Сохранение документа
        doc.build(story)
        logger.info(f"PDF сохранен в файл: {filename}")