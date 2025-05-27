import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
from jira import JIRA
from jira.exceptions import JIRAError
from config import JiraConfig
from openai_analyzer import MeetingAnalysis

logger = logging.getLogger(__name__)


class JiraIntegration:
    """Класс для интеграции с Jira"""

    def __init__(self, config: JiraConfig):
        """
        Инициализация интеграции с Jira

        Args:
            config: Конфигурация Jira
        """
        self.config = config

        try:
            # Подключение к Jira с использованием библиотеки python-jira
            self.jira = JIRA(
                server=config.url,
                basic_auth=(config.email, config.api_token)
            )

            # Проверка подключения
            self.jira.myself()
            logger.info(f"Успешное подключение к Jira: {config.url}")

        except JIRAError as e:
            logger.error(f"Ошибка подключения к Jira: {e}")
            raise
        except Exception as e:
            logger.error(f"Неожиданная ошибка при подключении к Jira: {e}")
            raise

    def check_project_exists(self, project_key: str) -> bool:
        """
        Проверка существования проекта

        Args:
            project_key: Ключ проекта

        Returns:
            bool: True если проект существует
        """
        try:
            self.jira.project(project_key)
            return True
        except JIRAError:
            logger.warning(f"Проект {project_key} не найден")
            return False

    def get_issue_types(self, project_key: str) -> List[str]:
        """
        Получение доступных типов задач для проекта

        Args:
            project_key: Ключ проекта

        Returns:
            List[str]: Список типов задач
        """
        try:
            project = self.jira.project(project_key)
            issue_types = [issue_type.name for issue_type in project.issueTypes]
            logger.info(f"Доступные типы задач: {issue_types}")
            return issue_types
        except JIRAError as e:
            logger.error(f"Ошибка получения типов задач: {e}")
            return ["Task", "Sub-task"]

    def create_main_issue_description(self, analysis: MeetingAnalysis) -> str:
        """
        Создание описания для основной задачи

        Args:
            analysis: Анализ совещания

        Returns:
            str: Описание в формате Jira
        """
        tasks_summary = ""
        if analysis.tasks:
            tasks_summary = "\n".join([
                f"• {task.get('название', 'Без названия')} - {task.get('суть_задачи', 'Суть не указана')} "
                f"(Исполнитель: {task.get('кто_выполняет', 'Не назначен')}, Срок: {task.get('срок', 'Не указан')})"
                for task in analysis.tasks
            ])

        description = f"""
h2. Резюме совещания
{analysis.summary}

h2. Участники
{', '.join(analysis.participants) if analysis.participants else 'Не определены'}

h2. Технические области
{', '.join(analysis.technical_areas) if analysis.technical_areas else 'Не определены'}

h2. Выявленные задачи ({len(analysis.tasks)})
{tasks_summary if tasks_summary else 'Задачи не выявлены'}

h2. Принятые решения ({len(analysis.decisions)})
{chr(10).join([f'* {decision}' for decision in analysis.decisions]) if analysis.decisions else 'Решения не выделены'}

h2. Гипотезы для проверки ({len(analysis.hypotheses)})
{chr(10).join([f'* {hyp["hypothesis"]} - {hyp.get("status", "требует проверки")}' for hyp in analysis.hypotheses]) if analysis.hypotheses else 'Гипотезы не выделены'}

h2. Метаданные
* Дата анализа: {datetime.now().strftime('%d.%m.%Y %H:%M')}
* Длина транскрипции: {len(analysis.transcript)} символов
* Метод анализа: OpenAI Tool Calling
"""
        return description

    def create_subtask_description(self, task: Dict[str, Any]) -> str:
        """
        Создание описания для подзадачи

        Args:
            task: Данные задачи

        Returns:
            str: Описание в формате Jira
        """
        return f"""
h3. Суть задачи
{task.get('суть_задачи', 'Суть не указана')}

h3. Подробное описание
{task.get('описание', 'Описание не предоставлено')}

h3. Ответственный
{task.get('кто_выполняет', 'Не назначен')}

h3. Срок выполнения
{task.get('срок', 'Не указан')}

h3. Источник
Автоматически извлечено из транскрипции технического совещания
"""

    def validate_assignee(self, assignee: str) -> Optional[str]:
        """
        Проверка существования пользователя в Jira

        Args:
            assignee: Имя пользователя или email

        Returns:
            Optional[str]: Валидное имя пользователя или None
        """
        if not assignee or assignee == "Не назначен":
            return None

        try:
            # Поиск пользователя
            users = self.jira.search_users(assignee, maxResults=1)
            if users:
                logger.info(f"Найден пользователь: {users[0].displayName}")
                return users[0].name
            else:
                logger.warning(f"Пользователь '{assignee}' не найден в Jira")
                return None
        except JIRAError as e:
            logger.warning(f"Ошибка поиска пользователя '{assignee}': {e}")
            return None

    def parse_due_date(self, date_string: str) -> Optional[str]:
        """
        Парсинг и валидация даты

        Args:
            date_string: Строка с датой

        Returns:
            Optional[str]: Дата в формате YYYY-MM-DD или None
        """
        if not date_string or date_string == "Не указан":
            return None

        # Попытка парсинга различных форматов
        formats = ['%Y-%m-%d', '%d.%m.%Y', '%d/%m/%Y']

        for fmt in formats:
            try:
                parsed_date = datetime.strptime(date_string, fmt)
                return parsed_date.strftime('%Y-%m-%d')
            except ValueError:
                continue

        logger.warning(f"Не удалось распарсить дату: {date_string}")
        return None

    def create_main_issue(self, analysis: MeetingAnalysis, project_key: str) -> str:
        """
        Создание основной задачи в Jira

        Args:
            analysis: Анализ совещания
            project_key: Ключ проекта

        Returns:
            str: Ключ созданной задачи
        """
        try:
            issue_dict = {
                'project': {'key': project_key},
                'summary': f"Техническое совещание - {datetime.now().strftime('%d.%m.%Y %H:%M')}",
                'description': self.create_main_issue_description(analysis),
                'issuetype': {'name': 'Task'},
                'labels': ['техническое-совещание', 'автоматический-анализ']
            }

            new_issue = self.jira.create_issue(fields=issue_dict)
            logger.info(f"Создана основная задача: {new_issue.key}")

            return new_issue.key

        except JIRAError as e:
            logger.error(f"Ошибка создания основной задачи: {e}")
            raise

    def create_subtask(self, task: Dict[str, Any], parent_key: str, project_key: str) -> str:
        """
        Создание подзадачи в Jira

        Args:
            task: Данные задачи
            parent_key: Ключ родительской задачи
            project_key: Ключ проекта

        Returns:
            str: Ключ созданной подзадачи
        """
        try:
            issue_dict = {
                'project': {'key': project_key},
                'parent': {'key': parent_key},
                'summary': task.get('название', 'Задача без названия'),
                'description': self.create_subtask_description(task),
                'issuetype': {'name': 'Sub-task'},
                'labels': ['автоматическая-задача']
            }

            # Добавление исполнителя если он валиден
            assignee = self.validate_assignee(task.get('кто_выполняет'))
            if assignee:
                issue_dict['assignee'] = {'name': assignee}

            # Добавление срока выполнения
            due_date = self.parse_due_date(task.get('срок'))
            if due_date:
                issue_dict['duedate'] = due_date

            new_issue = self.jira.create_issue(fields=issue_dict)
            logger.info(f"Создана подзадача: {new_issue.key} - {task.get('название')}")

            return new_issue.key

        except JIRAError as e:
            logger.error(f"Ошибка создания подзадачи '{task.get('название')}': {e}")
            raise

    def create_issues_from_analysis(self, analysis: MeetingAnalysis, project_key: str = None) -> Dict[str, Any]:
        """
        Создание задач в Jira на основе анализа

        Args:
            analysis: Анализ совещания
            project_key: Ключ проекта (по умолчанию из конфига)

        Returns:
            Dict: Результат создания задач
        """
        if not project_key:
            project_key = self.config.project_key

        logger.info(f"Создание задач в проекте {project_key}...")

        # Проверка проекта
        if not self.check_project_exists(project_key):
            raise ValueError(f"Проект {project_key} не существует")

        try:
            # Создание основной задачи
            main_issue_key = self.create_main_issue(analysis, project_key)

            # Создание подзадач
            subtask_keys = []
            for i, task in enumerate(analysis.tasks):
                try:
                    subtask_key = self.create_subtask(task, main_issue_key, project_key)
                    subtask_keys.append(subtask_key)
                except Exception as e:
                    logger.error(f"Не удалось создать подзадачу {i + 1}: {e}")
                    continue

            result = {
                "status": "success",
                "main_issue": main_issue_key,
                "subtasks": subtask_keys,
                "project_key": project_key,
                "created_at": datetime.now().isoformat(),
                "stats": {
                    "total_tasks": len(analysis.tasks),
                    "created_tasks": len(subtask_keys),
                    "failed_tasks": len(analysis.tasks) - len(subtask_keys),
                    "participants": len(analysis.participants),
                    "decisions": len(analysis.decisions),
                    "hypotheses": len(analysis.hypotheses)
                }
            }

            logger.info(f"Создание завершено: {len(subtask_keys)}/{len(analysis.tasks)} задач создано")
            return result

        except Exception as e:
            logger.error(f"Ошибка при создании задач в Jira: {e}")
            return {
                "status": "error",
                "message": str(e),
                "project_key": project_key,
                "created_at": datetime.now().isoformat()
            }

    def get_issue_url(self, issue_key: str) -> str:
        """
        Получение URL задачи

        Args:
            issue_key: Ключ задачи

        Returns:
            str: URL задачи
        """
        return f"{self.config.url}/browse/{issue_key}"

    def add_comment_to_issue(self, issue_key: str, comment: str):
        """
        Добавление комментария к задаче

        Args:
            issue_key: Ключ задачи
            comment: Текст комментария
        """
        try:
            self.jira.add_comment(issue_key, comment)
            logger.info(f"Добавлен комментарий к задаче {issue_key}")
        except JIRAError as e:
            logger.error(f"Ошибка добавления комментария: {e}")
