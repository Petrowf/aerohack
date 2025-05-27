import logging
import os

import requests
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from config import WeeekConfig
from openai_analyzer import MeetingAnalysis

logger = logging.getLogger(__name__)


class WeeekIntegration:
    """Класс для интеграции с Weeek API v1"""

    def __init__(self, config: WeeekConfig):
        """
        Инициализация интеграции с Weeek

        Args:
            config: Конфигурация Weeek
        """
        self.config = config
        self.base_url = "https://api.weeek.net/public/v1"
        self.headers = {
            "Authorization": f"Bearer {config.api_token}",
            "Content-Type": "application/json"
        }

        # Проверка подключения
        try:
            self._check_connection()
            logger.info(f"Успешное подключение к Weeek API")
        except Exception as e:
            logger.error(f"Ошибка подключения к Weeek: {e}")
            raise

    def _check_connection(self):
        """Проверка подключения к API"""
        url = f"{self.base_url}/user/me"
        response = requests.get(url, headers=self.headers)

        if response.status_code != 200:
            raise Exception(f"Ошибка подключения к Weeek API: {response.status_code} - {response.text}")

        user_data = response.json()
        logger.info(f"Подключен пользователь: {user_data.get('user', {}).get('firstName', 'Неизвестно')}")

    def _make_request(self, method: str, endpoint: str, data: Dict = None, params: Dict = None) -> Dict[str, Any]:
        """
        Выполнение запроса к API

        Args:
            method: HTTP метод
            endpoint: Конечная точка API (без базового URL)
            data: Данные для отправки в body
            params: Параметры для URL

        Returns:
            Dict: Ответ API
        """
        url = f"{self.base_url}/{endpoint}"

        try:
            if method.upper() == "GET":
                response = requests.get(url, headers=self.headers, params=params)
            elif method.upper() == "POST":
                response = requests.post(url, headers=self.headers, json=data)
            elif method.upper() == "PUT":
                response = requests.put(url, headers=self.headers, json=data)
            elif method.upper() == "PATCH":
                response = requests.patch(url, headers=self.headers, json=data)
            elif method.upper() == "DELETE":
                response = requests.delete(url, headers=self.headers)
            else:
                raise ValueError(f"Неподдерживаемый HTTP метод: {method}")

            response.raise_for_status()
            return response.json()

        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка запроса к {url}: {e}")
            if hasattr(e, 'response') and e.response:
                logger.error(f"Ответ сервера: {e.response.text}")
            raise


    def get_workspace_members(self) -> List[Dict[str, Any]]:
        """
        Получение участников workspace

        Returns:
            List[Dict]: Список участников
        """
        try:
            response = self._make_request("GET", "ws/members")
            return response.get("members", [])
        except Exception as e:
            logger.error(f"Ошибка получения участников workspace: {e}")
            return []



    def get_project_by_id(self, project_id: str) -> Optional[Dict[str, Any]]:
        """
        Получение проекта по ID

        Args:
            project_id: ID проекта

        Returns:
            Optional[Dict]: Данные проекта
        """
        try:
            response = self._make_request("GET", f"tm/projects/{project_id}")
            return response.get("project", {})
        except Exception as e:
            logger.error(f"Ошибка получения проекта {project_id}: {e}")
            return None


    def create_board(self, project_id: str, title: str, description: str = "") -> Dict[str, Any]:
        """
        Создание доски в проекте

        Args:
            project_id: ID проекта
            title: Название доски
            description: Описание доски

        Returns:
            Dict: Данные созданной доски
        """
        board_data = {
            "title": title,
            "description": description
        }

        try:
            response = self._make_request("POST", f"tm/projects/{project_id}/boards", board_data)
            return response.get("board", {})
        except Exception as e:
            logger.error(f"Ошибка создания доски: {e}")
            raise

    def get_tasks(self, board_id: str = None, project_id: str = None) -> List[Dict[str, Any]]:
        """
        Получение задач

        Args:
            board_id: ID доски (опционально)
            project_id: ID проекта (опционально)

        Returns:
            List[Dict]: Список задач
        """
        params = {}
        if board_id:
            params["boardId"] = board_id
        if project_id:
            params["projectId"] = project_id

        try:
            response = self._make_request("GET", "tm/tasks", params=params)
            return response.get("tasks", [])
        except Exception as e:
            logger.error(f"Ошибка получения задач: {e}")
            return []

    def find_user_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Поиск пользователя по имени или email

        Args:
            name: Имя пользователя или email

        Returns:
            Optional[Dict]: Данные пользователя
        """
        members = self.get_workspace_members()

        name_lower = name.lower()
        for member in members:
            # Поиск по email
            if member.get("email", "").lower() == name_lower:
                return member

            # Поиск по имени
            first_name = member.get("firstName", "").lower()
            last_name = member.get("lastName", "").lower()
            full_name = f"{first_name} {last_name}".strip()

            if (first_name == name_lower or
                    last_name == name_lower or
                    full_name == name_lower):
                return member

        logger.warning(f"Пользователь '{name}' не найден")
        return None

    def parse_due_date(self, date_string: str) -> Optional[str]:
        """
        Парсинг и валидация даты для Weeek

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

        # Если дата в относительном формате
        relative_dates = {
            "завтра": 1,
            "послезавтра": 2,
            "через неделю": 7,
            "через две недели": 14,
            "через месяц": 30
        }

        for phrase, days in relative_dates.items():
            if phrase in date_string.lower():
                future_date = datetime.now() + timedelta(days=days)
                return future_date.strftime('%Y-%m-%d')

        logger.warning(f"Не удалось распарсить дату: {date_string}")
        return None

    def create_task(self,
                    title: str,
                    description: str,
                    board_id: str,
                    assignees: List[str] = None,
                    due_date: str = None,
                    parent_id: int = None) -> Dict[str, Any]:
        """
        Создание задачи в Weeek

        Args:
            title: Название задачи
            description: Описание задачи
            board_id: ID доски
            assignees: Список ID исполнителей
            due_date: Срок выполнения в формате YYYY-MM-DD

        Returns:
            Dict: Данные созданной задачи
        """
        task_data = {
            "title": title,
            "description": description,
            "boardId": board_id,
            "parentId": parent_id
        }

        # Добавление исполнителей
        if assignees:
            task_data["assignees"] = assignees

        # Добавление срока выполнения
        if due_date:
            parsed_date = self.parse_due_date(due_date)
            if parsed_date:
                task_data["dueDate"] = parsed_date

        try:
            response = self._make_request("POST", "tm/tasks", task_data)
            return response.get("task", {})
        except Exception as e:
            logger.error(f"Ошибка создания задачи '{title}': {e}")
            raise


    def create_summary_task(self, analysis: MeetingAnalysis, board_id: str) -> Dict[str, Any]:
        """
        Создание сводной задачи с результатами совещания

        Args:
            analysis: Анализ совещания
            board_id: ID доски

        Returns:
            Dict: Данные созданной задачи
        """
        title = f"📋 Сводка совещания от {datetime.now().date()}"

        description = f"""Результаты совещания

👥 Председатель: {analysis.president if analysis.president else "Не определен"}
👥 Секретарь: {analysis.secretary if analysis.secretary else "Не определен"}

📝 Резюме {analysis.summary}

✅ Принятые решения ({len(analysis.decisions)})
{chr(10).join([f'• {decision}' for decision in analysis.decisions]) if analysis.decisions else 'Решения не принимались'}

🔬 Гипотезы для проверки ({len(analysis.hypotheses)})
{chr(10).join([f'• {hyp["hypothesis"]} - {hyp.get("status", "требует проверки")}' for hyp in analysis.hypotheses]) if analysis.hypotheses else 'Гипотезы не выдвигались'}

👥 Участники
{', '.join(analysis.participants) if analysis.participants else 'Не определены'}

👥 Отсутствовавшие
{', '.join(analysis.absent) if analysis.absent else 'Не определены'}

---
🤖 Автоматически создано на основе анализа транскрипции
📅 Дата создания: {datetime.now().strftime('%d.%m.%Y в %H:%M')}"""

        try:
            return self.create_task(
                title=title,
                description=description,
                board_id=board_id
            )
        except Exception as e:
            logger.error(f"Ошибка создания сводной задачи: {e}")
            raise

    def create_tasks_from_analysis(self, analysis: MeetingAnalysis) -> Dict[str, Any]:
        """
        Создание задач в Weeek на основе анализа

        Args:
            analysis: Анализ совещания
            project_id: ID проекта (если None, создается новый)

        Returns:
            Dict: Результат создания задач
        """
        logger.info("Создание задач в Weeek...")

        project_id = self.config.project_id

        # Проверка проекта
        project = self.get_project_by_id(project_id)
        if not project:
            raise ValueError(f"Проект {project_id} не найден")

        board_id = os.getenv("WEEEK_BOARD_ID")

        created_tasks = []
        failed_tasks = []

        try:
            # Создание сводной задачи
            summary_task = self.create_summary_task(analysis, board_id)
            main_task_id = summary_task.get("id")
            created_tasks.append({
                "id": main_task_id,
                "title": summary_task.get("title"),
                "type": "summary"
            })

            # Создание задач из анализа
            for i, task_data in enumerate(analysis.tasks):
                try:
                    # Поиск исполнителей
                    assignees = []
                    assignee_name = task_data.get('кто_выполняет')
                    if assignee_name and assignee_name != "Не назначен":
                        user = self.find_user_by_name(assignee_name)
                        if user:
                            assignees.append(user.get("id"))

                    # Создание задачи
                    task = self.create_task(
                        title=task_data.get('название', f'Задача {i + 1}'),
                        description=f"""📋 {task_data.get('суть_задачи', 'Суть не указана')}

📝 Подробное описание:
{task_data.get('описание', 'Описание не предоставлено')}

👤 Ответственный: {task_data.get('кто_выполняет', 'Не назначен')}
📅 Срок: {task_data.get('срок', 'Не указан')}

---
🤖 Автоматически извлечено из транскрипции совещания""",
                        board_id=board_id,
                        assignees=assignees if assignees else None,
                        due_date=task_data.get('срок'),
                        parent_id=main_task_id
                    )

                    created_tasks.append({
                        "id": task.get("id"),
                        "title": task.get("title"),
                        "type": "task",
                        "assignee": assignee_name,
                        "parent_id": main_task_id
                    })

                    logger.info(f"Создана задача: {task_data.get('название')}")

                except Exception as e:
                    logger.error(f"Не удалось создать задачу {i + 1}: {e}")
                    failed_tasks.append({
                        "index": i + 1,
                        "title": task_data.get('название', f'Задача {i + 1}'),
                        "error": str(e)
                    })

            # Формирование результата
            result = {
                "status": "success",
                "project": {
                    "id": project_id,
                    "title": project.get("title"),
                },
                "board": {
                    "id": board_id
                },
                "tasks": created_tasks,
                "failed_tasks": failed_tasks,
                "created_at": datetime.now().isoformat(),
                "stats": {
                    "total_tasks": len(analysis.tasks),
                    "created_tasks": len([t for t in created_tasks if t["type"] == "task"]),
                    "failed_tasks": len(failed_tasks),
                    "summary_task": 1,
                    "participants": len(analysis.participants),
                    "decisions": len(analysis.decisions),
                    "hypotheses": len(analysis.hypotheses)
                }
            }

            logger.info(f"Создание завершено: {len(created_tasks)} задач создано в проекте {project.get('title')}")
            return result

        except Exception as e:
            logger.error(f"Ошибка при создании задач в Weeek: {e}")
            return {
                "status": "error",
                "message": str(e),
                "project_id": project_id,
                "created_at": datetime.now().isoformat(),
                "partial_results": {
                    "created_tasks": created_tasks,
                    "failed_tasks": failed_tasks
                }
            }
