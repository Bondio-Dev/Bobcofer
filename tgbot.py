from __future__ import annotations
# в самый верх tgbot.py (до остальных import-ов)

import json, logging
from datetime import datetime, timezone
import csv
from report import generate_delivery_stats_report

class JsonFormatter(logging.Formatter):
    """
    Пишет единичную запись в bot.log:
    
    "time": "2025-07-20 02:05:31",
    "template": "",
    "funnel": "Новый клиент", 
    "phone": "+7981…",
    "success": true,
    "error": "",
    "msg": "любое сообщение, переданное logger.*"
    
    """
    def format(self, record: logging.LogRecord) -> str:
        log_record = {
            "time": datetime.now(timezone.utc).replace(microsecond=0)
                    .isoformat(sep=' '), # <- fix utcnow()
            "template": getattr(record, "template", ""),
            "funnel": getattr(record, "funnel", ""), 
            "phone": getattr(record, "phone", ""), # добавили номер
            "success": getattr(record, "success", ""), # единое поле OK/Fail
            "error": getattr(record, "err", ""), # текст ошибки/исключения
            "msg": record.getMessage(),
        }
        return json.dumps(log_record, ensure_ascii=False) # (+)

import asyncio
import os
import re
import sys
import uuid
import time
from datetime import datetime, timedelta, timezone
from itertools import islice
from pathlib import Path
import ssl
import csv
import uuid
import os
from aiogram.fsm.state import State, StatesGroup

import aiohttp
import phonenumbers
import requests
from aiogram import Bot, Dispatcher, Router, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
import pywhatkit

# ---------------------------------------------------------------------------
# Настройки
BASE_DIR = Path(__file__).parent
TOKEN_FILE = BASE_DIR / "token.json"
CONTACTS_FILE = BASE_DIR / "contacts.json"
MAIN_DATA = BASE_DIR / "data.json"

# API настройки (из bot.py)
TEMPLATES_FILE = BASE_DIR / "templates.json"

import random
def get_random_wait_time():
    return random.randint(10, 45)

AMOCRM_DIR = BASE_DIR / "amocrm_contacts"
TEMP_CONTACTS_DIR = BASE_DIR / "temp_contacts"  # ← НОВАЯ СТРОКА
AMOCRM_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# Логирование в формате JSON
LOG_FILE = BASE_DIR / "bot.log"
_json_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
_json_handler.setFormatter(JsonFormatter())

# сразу после создания _json_handler
_console = logging.StreamHandler()
_console.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))

logging.basicConfig(level=logging.INFO, handlers=[_json_handler, _console])
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Функция логирования из bot.py
def log_message(
    phone: str,
    success: bool,
    response_text: str = "",
    template_id: str = "",
    funnel: str = ""
):
    """
    Записывает строку лога в конец CSV-файла. Не создаёт файл и не пишет заголовки.
    Предполагается, что файл logs/delivery_logs.csv уже существует и имеет правильные заголовки.
    """
    log_file = "logs/delivery_logs.csv"
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status = "SUCCESS" if success else "FAILED"
    phone_str = str(phone)
    template_id = template_id or "-"
    funnel = funnel or "-"
    response_text = response_text.replace("\n", " ").replace("\r", " ") if response_text else ""
    response_text = response_text[:300]
    
    with open(log_file, mode='a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([ts, phone_str, template_id, funnel, status, response_text])

# ---------------------------------------------------------------------------
# Функция отправки из bot.py (синхронная версия)
def send_message_sync(dest: str, message: str, funnel: str = "") -> tuple[int, str]:
    """Отправка сообщения через PyWhatKit"""
    try:
        # Форматируем номер телефона
        if not dest.startswith('+'):
            dest = '+' + dest
            
        # Отправляем сообщение
        pywhatkit.sendwhatmsg_instantly(
            phone_no=dest,
            message=message,
            wait_time=get_random_wait_time(),
            tab_close=True
        )
        
        log_message(dest, True, "Отправлено", "pywhatkit", funnel)
        return 202, "Сообщение отправлено"
        
    except Exception as e:
        error_msg = f"Ошибка PyWhatKit: {e}"
        log_message(dest, False, error_msg, "pywhatkit", funnel)
        return 0, error_msg

# ---------------------------------------------------------------------------
async def send_message_async(dest: str, message: str, funnel: str = "-") -> tuple[int, str]:
    """Асинхронная отправка сообщения через Telegram Bot API"""
    try:
        token = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))["BOT_TOKEN"]
        import aiohttp
        import ssl
        
        # Создаем SSL контекст который не проверяет сертификаты
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        
        connector = aiohttp.TCPConnector(ssl=ssl_context)
        
        async with aiohttp.ClientSession(connector=connector) as session:
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            data = {
                "chat_id": dest,
                "text": message,
                "parse_mode": "HTML"
            }
            
            async with session.post(url, data=data) as response:
                status_code = response.status
                response_text = await response.text()
                
                ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                phone_str = str(dest)
                template_id = "text_template"
                status = "SUCCESS" if status_code == 200 else "FAILED"
                
                with open('logs/delivery_logs.csv', mode='a', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow([ts, phone_str, template_id, funnel, status, response_text[:100]])
                
                return status_code, response_text
                
    except Exception as e:
        logger.exception(f"Ошибка отправки сообщения: {e}")
        return 500, str(e)


# ---------------------------------------------------------------------------
# 5. Утилита чтения логов (bot.log + delivery_logs.txt)
def load_reports():
    """
    Возвращает структуру:
    
    (date, template_id): {
        "total": N,
        "ok": M,
        "fail": K,
        "bad": [(phone, error), ...]
    },
    ...
    
    """
    stats: dict[tuple[str, str], dict] = {}
    txt_path = BASE_DIR / "logs" / "delivery_logs.txt"
    if not txt_path.exists():
        return stats
    
    for line in txt_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split("|")]
        
        # Пропускаем строки, которые не являются основными записями лога
        # (например, части JSON-ответов)
        if len(parts) < 5:
            continue
            
        # НОВЫЙ ФОРМАТ: timestamp | phone | template_id | funnel | STATUS | response_text
        try:
            timestamp = parts[0]
            phone = parts[1]
            template_id = parts[2] if parts[2] != "-" else "unknown"
            funnel = parts[3] if parts[3] != "-" else ""
            status = parts[4]
            response_text = parts[5] if len(parts) > 5 else ""
            
            # Извлекаем дату
            date = timestamp.split()[0]
            key = (date, template_id)
            rec = stats.setdefault(key, {
                "total": 0,
                "ok": 0,
                "fail": 0,
                "bad": []
            })
            
            rec["total"] += 1
            if status == "SUCCESS":
                rec["ok"] += 1
            else:
                rec["fail"] += 1
                # Извлекаем краткое описание ошибки из response_text
                error_msg = response_text[:100] if response_text else "Unknown error"
                rec["bad"].append((phone, error_msg))
                
        except (IndexError, ValueError) as e:
            # Логируем проблемные строки для отладки
            logger.debug(f"Не удалось распарсить строку лога: {line[:100]}... Ошибка: {e}")
            continue
    
    return stats

MENU_BUTTONS = [
    ["Выбрать воронку"],
    ["Просмотр шаблонов"],
    ["Просмотр запланированных"],
    ["Просмотр админов"],
    ["Просмотреть отчёты"],
    ["🏠 Главное меню"]  # ← ДОБАВИТЬ ЭТУ СТРОКУ
]

def create_persistent_main_menu():
    """Создает главное меню с постоянной клавиатурой"""
    keyboard = [
        [KeyboardButton(text=row[0])] for row in MENU_BUTTONS
    ]
    
    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        is_persistent=True,  # ← КЛЮЧЕВОЙ ПАРАМЕТР - клавиатура всегда видна
        one_time_keyboard=False,
        input_field_placeholder="Выберите действие"
    )

# ---------------------------------------------------------------------------
# States
from aiogram.fsm.state import State, StatesGroup

class Form(StatesGroup):
    STATE_MENU             = State()
    STATE_TEMPLATE_CHOOSE  = State()
    STATE_TEMPLATE_CONFIRM = State()
    STATE_TEMPLATE_NEW_1   = State()
    STATE_TEMPLATE_NEW_2   = State()
    STATE_TEMPLATE_VIEW    = State()
    STATE_AUDIENCE         = State()
    STATE_TIME_CHOOSE      = State()
    STATE_TIME_INPUT       = State()
    STATE_TIME_RANGE       = State()   # ← добавлено
    STATE_CONFIRM          = State()
    STATE_ADMIN_ADD        = State()
    STATE_AMOCRM_INPUT     = State()
    STATE_AMOCRM_FILENAME  = State()
    STATE_REPORT_LIST      = State()
    STATE_REPORT_DETAIL    = State()
    STATE_PHOTO_UPLOAD = State()



# ---------------------------------------------------------------------------
# AmoCRM manager
class AmoCRMCategoryManager:
    def __init__(self) -> None:
        cfg_path = os.path.join(os.path.dirname(__file__), "conf.json")
        with open(cfg_path, encoding="utf-8") as fh:
            cfg = json.load(fh)
        acc = cfg["amocrm"]
        self.subdomain: str = acc["subdomain"]
        self.access_token: str = acc["access_token"]
        self._base_urls = [
            f"https://{self.subdomain}.amocrm.ru/api/v4",
            f"https://{self.subdomain}.kommo.com/api/v4",
        ]
        self.headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        self.base_url: str = self._detect_base_url()

    def _detect_base_url(self) -> str:
        for url in self._base_urls:
            try:
                if (
                    requests.get(
                        f"{url}/account", headers=self.headers, timeout=6
                    ).status_code
                    == 200
                ):
                    return url
            except requests.exceptions.RequestException:
                pass
        raise RuntimeError("Не удалось найти рабочий домен Kommo")

    def get_pipelines(self) -> list[tuple[int, str]]:
        r = requests.get(
            f"{self.base_url}/leads/pipelines", headers=self.headers, timeout=20
        )
        r.raise_for_status()
        return [(p["id"], p["name"]) for p in r.json()["_embedded"]["pipelines"]]

    def get_pipeline_statuses(self, pipeline_id: int) -> list[tuple[int, str]]:
        """Получить статусы пайплайна с фильтрацией системных этапов"""
        r = requests.get(
            f"{self.base_url}/leads/pipelines/{pipeline_id}/statuses",
            headers=self.headers,
            timeout=20
        )
        r.raise_for_status()
        
        # Системные этапы для исключения
        system_stages = ['Неразобранное', 'Успешно реализовано', 'Закрыто и не реализовано']
        
        statuses = []
        for status in r.json()["_embedded"]["statuses"]:
            status_name = status["name"]
            if status_name not in system_stages:
                statuses.append((status["id"], status_name))
        
        return statuses

    def get_leads(self, pipeline_id: int, status_id: int) -> list[dict]:
        out, page = [], 1
        while True:
            params = {
                "limit": 250,
                "page": page,
                "filter[statuses][0][pipeline_id]": pipeline_id,
                "filter[statuses][0][status_id]": status_id,
                "with": "contacts",
            }
            r = requests.get(
                f"{self.base_url}/leads",
                headers=self.headers,
                params=params,
                timeout=20,
            )
            if r.status_code == 204:
                break
            r.raise_for_status()
            batch = r.json()["_embedded"]["leads"]
            if not batch:
                break
            out.extend(batch)
            page += 1
        return out

    def get_leads_all_statuses(self, pipeline_id: int) -> list[dict]:
        """Возвращает все сделки во всех статусах указанной воронки."""
        all_leads = []
        for status_id, _ in self.get_pipeline_statuses(pipeline_id):
            all_leads.extend(self.get_leads(pipeline_id, status_id))
        return all_leads

    def get_contacts_bulk(self, ids: list[int]) -> dict[int, dict]:
        result: dict[int, dict] = {}
        ids_iter = iter(ids)
        while chunk := list(islice(ids_iter, 200)):
            params = {"with": "custom_fields_values"}
            params.update({f"id[{i}]": cid for i, cid in enumerate(chunk)})
            r = requests.get(
                f"{self.base_url}/contacts",
                headers=self.headers,
                params=params,
                timeout=20,
            )
            if r.status_code != 200:
                continue
            for c in r.json()["_embedded"]["contacts"]:
                result[c["id"]] = c
        return result

    @staticmethod
    def extract_phone(cfv: list[dict]) -> str:
        for fld in cfv or []:
            if fld.get("field_code") == "PHONE":
                for val in fld.get("values", []):
                    phone = str(val.get("value", "")).strip()
                    if phone:
                        return phone
        return ""

    @staticmethod
    def normalize_phone(phone: str):
        digits = re.sub(r"\D", "", phone)
        if digits.startswith("8") and len(digits) == 11:
            digits = "7" + digits[1:]
        elif digits.startswith("7") and len(digits) == 11:
            pass
        elif digits.startswith("9") and len(digits) == 10:
            digits = "7" + digits
        digits = "+" + digits
        try:
            parsed = phonenumbers.parse(digits, None)
            if phonenumbers.is_valid_number(parsed):
                return phonenumbers.format_number(
                    parsed, phonenumbers.PhoneNumberFormat.E164
                )
        except phonenumbers.phonenumberutil.NumberParseException:
            pass
        return False

# ---------------------------------------------------------------------------
from main import build_funnels_snapshot



# ---------------------------------------------------------------------------
# Обновляем список воронок: чистим папку и пишем funnels.json
async def update_amocrm_funnels() -> str:
    attempt = 0
    max_attempts = 3
    pause_seconds = 10
    
    # Чистим папку один раз в начале
    for f in AMOCRM_DIR.glob("*.json"):
        try:
            f.unlink()
        except Exception:
            logger.warning("Не смог удалить %s", f)
    
    # Цикл с повторными попытками
    while attempt < max_attempts:
        try:
            snap = await asyncio.to_thread(build_funnels_snapshot)
            return f"✅ Снято {len(snap['funnels'])} воронок, контакты очищены."
        except Exception as e:
            attempt += 1
            logger.exception(f"build_funnels_snapshot попытка {attempt}/{max_attempts} неудачна: %s", e)
            
            if attempt < max_attempts:
                logger.info(f"Пауза {pause_seconds} секунд перед следующей попыткой...")
                await asyncio.sleep(pause_seconds)
            else:
                logger.error("Все попытки подключения к AmoCRM исчерпаны")
                return "❌ Сервер AmoCRM не отвечает, попробуйте снова через несколько минут"
    
    # Этот код никогда не должен выполниться, но на всякий случай
    return "❌ Неожиданная ошибка при обновлении воронок"


class JSONStore:
    def __init__(self, path: Path):
        self.path = path

    def read(self) -> list:
        """Read data from JSON file with proper error handling"""
        try:
            if not self.path.exists():
                return []
            
            content = self.path.read_text(encoding="utf-8").strip()
            if not content:
                return []
                
            return json.loads(content)
        except (json.JSONDecodeError, FileNotFoundError) as e:
            logger.warning(f"Error reading {self.path}: {e}. Returning empty list.")
            return []
        except Exception as e:
            logger.error(f"Unexpected error reading {self.path}: {e}")
            return []

    def write(self, data: list):
        """Write data to JSON file"""
        try:
            self.path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), 
                encoding="utf-8"
            )
        except Exception as e:
            logger.error(f"Error writing to {self.path}: {e}")

    def append(self, item):
        """Append item to the list"""
        data = self.read()
        data.append(item)
        self.write(data)

    def remove(self, predicate_func):
        """Remove items matching predicate"""
        data = self.read()
        filtered = [item for item in data if not predicate_func(item)]
        self.write(filtered)


admins_store = JSONStore(BASE_DIR / "admins.json")
scheduled_store = JSONStore(BASE_DIR / "scheduled.json")

def admin_required(func):
    async def wrapper(message_or_query, state: FSMContext, *args, **kwargs):
        user_id = (
            message_or_query.from_user.id
            if isinstance(message_or_query, (Message, CallbackQuery))
            else None
        )
        if user_id not in admins_store.read():
            if isinstance(message_or_query, CallbackQuery):
                await message_or_query.message.reply_text(f"❌ Доступ запрещён. Ваш ID: <code>{user_id}</code>")
            else:
                await message_or_query.reply(f"❌ Доступ запрещён. Ваш ID: <code>{user_id}</code>")
            return
        return await func(message_or_query, state)
    return wrapper

def ensure_dirs():
    """Ensure all required directories and files exist with proper initialization"""
    BASE_DIR.mkdir(exist_ok=True)
    AMOCRM_DIR.mkdir(exist_ok=True)
    TEMP_CONTACTS_DIR.mkdir(exist_ok=True)

    # Initialize token file
    if not TOKEN_FILE.exists():
        TOKEN_FILE.write_text('{"BOT_TOKEN": "YOUR_TOKEN_HERE"}', encoding="utf-8")

    # Initialize contacts file
    if not CONTACTS_FILE.exists():
        CONTACTS_FILE.write_text("[]", encoding="utf-8")

    # Initialize main data file
    if not MAIN_DATA.exists():
        MAIN_DATA.write_text('{"1": "", "2": ""}', encoding="utf-8")

    # Initialize templates file
    if not TEMPLATES_FILE.exists():
        default_templates = [
            {
                "id": "greeting",
                "name": "Приветствие",
                "content": "Привет, {name}! {message}"
            },
            {
                "id": "reminder",
                "name": "Напоминание", 
                "content": "Уважаемый {name}, напоминаем: {message}"
            }
        ]
        TEMPLATES_FILE.write_text(
            json.dumps(default_templates, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
    
    # Initialize scheduled jobs file (КЛЮЧЕВОЕ ИСПРАВЛЕНИЕ)
    scheduled_file = BASE_DIR / "scheduled.json"
    if not scheduled_file.exists() or scheduled_file.stat().st_size == 0:
        scheduled_file.write_text("[]", encoding="utf-8")
        logger.info("Initialized empty scheduled jobs file")
    
    # Initialize admins file
    admins_file = BASE_DIR / "admins.json"
    if not admins_file.exists() or admins_file.stat().st_size == 0:
        admins_file.write_text("[]", encoding="utf-8")
        logger.info("Initialized empty admins file")


def local_offset() -> timedelta:
    return datetime.now() - datetime.now(timezone.utc).replace(tzinfo=None)

def fmt_local(dt: datetime) -> str:
    return (dt + local_offset()).strftime("%d.%m.%Y %H:%M")

def now_tz():
    return datetime.now(timezone.utc)

def parse_datetime(text: str) -> datetime | None:
    try:
        dt_local = datetime.strptime(text, "%d.%m.%Y %H:%M")
        return (dt_local - local_offset()).replace(tzinfo=timezone.utc)
    except ValueError:
        return None

def render_message_main() -> str:
    try:
        data = json.loads(MAIN_DATA.read_text(encoding="utf-8"))
        return f'{data.get("1","")}\n{data.get("2","")}'
    except Exception:
        return "Нет данных"

# Замените функцию build_scheduled_rows (добавьте кнопку главного меню)
def build_scheduled_rows():
    """Build inline keyboard rows for scheduled jobs with error handling"""
    try:
        jobs = scheduled_store.read()
        
        # If no jobs, return empty list
        if not jobs:
            return []
        
        rows = []
        for j in jobs:
            try:
                # Validate job structure
                if not isinstance(j, dict) or 'run_at' not in j or 'job_id' not in j:
                    logger.warning(f"Invalid job structure: {j}")
                    continue
                    
                # Parse and format datetime
                run_at_str = j["run_at"]
                if isinstance(run_at_str, str):
                    run_at = datetime.fromisoformat(run_at_str)
                    formatted_time = fmt_local(run_at)
                else:
                    logger.warning(f"Invalid run_at format: {run_at_str}")
                    formatted_time = "Неверное время"
                
                rows.append([
                    InlineKeyboardButton(
                        text=formatted_time,
                        callback_data=f"job_detail:{j['job_id']}",
                    )
                ])
            except Exception as e:
                logger.error(f"Error processing job {j}: {e}")
                continue
        
        return rows
        
    except Exception as e:
        logger.error(f"Error in build_scheduled_rows: {e}")
        return []



# Замените функцию build_admin_rows (добавьте кнопку главного меню)
def build_admin_rows():
    admins = admins_store.read()
    rows = [
        [
            InlineKeyboardButton(
                text=str(a), callback_data=f"adm_detail:{a}"
            )
        ]
        for a in admins
    ]
    rows.append(
        [InlineKeyboardButton(text="➕ Добавить", callback_data="adm_add")]
    )
    rows.append(
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="to_main_menu")]
    )
    return rows



# ---------------------------------------------------------------------------
class SimpleJobQueue:
    def __init__(self):
        self.jobs = []

    async def run_once(self, callback, when: datetime, data, name: str):
        job = {"callback": callback, "when": when, "data": data, "name": name}
        self.jobs.append(job)

    async def process_jobs(self):
        while True:
            current_time = now_tz()
            jobs_to_run = [
                job for job in self.jobs if job["when"] <= current_time
            ]
            
            for job in jobs_to_run:
                try:
                    class JobContext:
                        def __init__(self, data):
                            self.data = data
                    
                    context = JobContext(job["data"])
                    await job["callback"](context)
                    self.jobs.remove(job)
                except Exception as e:
                    logger.exception(
                        f"Ошибка выполнения задачи {job['name']}: {e}"
                    )
            
            await asyncio.sleep(10)

job_queue = SimpleJobQueue()

#-----------------

import random
# ---------------------------------------------------------------------------
# 2) Функция отправки рассылки: подстановка имени в первый параметр
# 2) Полная функция отправки рассылки с учётом временного диапазона
async def job_send_distribution(context):
    try:
        job = context.data
        contacts_path = Path(job["contacts"])
        if not contacts_path.exists():
            logger.error("Контактный файл %s не найден", contacts_path)
            return

        contacts_data = json.loads(contacts_path.read_text("utf-8"))
        templates = json.loads(TEMPLATES_FILE.read_text("utf-8"))
        template = next((t for t in templates if t["id"] == job["template_id"]), None)
        if not template:
            logger.error("Шаблон %s не найден", job["template_id"])
            return

        day_from = datetime.strptime(job.get("day_from", "00:00"), "%H:%M").time()
        day_until = datetime.strptime(job.get("day_until", "23:59"), "%H:%M").time()
        photo_file_id = job.get("photo_file_id")

        for contact in contacts_data:
            while True:
                now_local = (now_tz() + local_offset()).time()
                if day_from <= now_local <= day_until:
                    break
                await asyncio.sleep(60)

            message = template["content"].format(
                name=contact["name"],
                message=json.loads(MAIN_DATA.read_text(encoding="utf-8"))["2"]
            )
            if photo_file_id:
                code, resp = await send_message_with_photo_async(
                    dest=contact["phone"],
                    message=message,
                    photo_file_id=photo_file_id,
                    funnel=job["job_id"]
                )
            else:
                code, resp = await send_message_async(
                    dest=contact["phone"],
                    message=message,
                    funnel=job["job_id"]
                )

            log_extra = {
                "template": job["template_id"],
                "funnel": job["job_id"],
                "phone": contact["phone"],
                "success": code == 202,
                "err": "" if code == 202 else resp
            }
            level = logging.INFO if code == 202 else logging.ERROR
            logger.log(level, "%s → %s", contact["phone"], "OK" if code == 202 else f"ERR {code}", extra=log_extra)
            pause_seconds = random.randint(10, 15) #исправить
            logger.info(f"Пауза между отправками: {pause_seconds} секунд")
            await asyncio.sleep(pause_seconds)

        scheduled_store.remove(lambda x: x["job_id"] == job["job_id"])
        logger.info("Рассылка %s завершена (%d номеров)", job["job_id"], len(contacts_data))

    except Exception:
        logger.exception("Ошибка в job_send_distribution")

async def send_message_with_photo_async(dest: str, message: str, photo_file_id: str, funnel: str = "-") -> tuple[int, str]:
    """Асинхронная отправка сообщения с фото через Telegram Bot API"""
    try:
        token = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))["BOT_TOKEN"]
        import aiohttp
        import ssl
        
        # Создаем SSL контекст который не проверяет сертификаты
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        
        connector = aiohttp.TCPConnector(ssl=ssl_context)
        
        async with aiohttp.ClientSession(connector=connector) as session:
            url = f"https://api.telegram.org/bot{token}/sendPhoto"
            data = {
                "chat_id": dest,
                "photo": photo_file_id,
                "caption": message,
                "parse_mode": "HTML"
            }
            
            async with session.post(url, data=data) as response:
                status_code = response.status
                response_text = await response.text()
                
                ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                phone_str = str(dest)
                template_id = "photo_template"
                status = "SUCCESS" if status_code == 200 else "FAILED"
                
                with open('logs/delivery_logs.csv', mode='a', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow([ts, phone_str, template_id, funnel, status, response_text[:100]])
                
                return status_code, response_text
                
    except Exception as e:
        logger.exception(f"Ошибка отправки фото: {e}")
        return 500, str(e)




# 2.7) Расширение функции schedule_job для сохранения диапазона
def schedule_job(run_at: datetime,
                contacts_file: Path,
                template_id: str,
                template_lang: str = "ru",
                day_from: str = "00:00",
                day_until: str = "23:59",
                photo_file_id: str = None) -> str:
    job_id = f"job_{uuid.uuid4().hex[:8]}"
    data = {
        "job_id": job_id,
        "run_at": run_at.isoformat(),
        "contacts": str(contacts_file),
        "template_id": template_id,
        "template_lang": template_lang,
        "day_from": day_from,
        "day_until": day_until,
    }
    if photo_file_id:
        data["photo_file_id"] = photo_file_id

    scheduled_store.append(data)
    asyncio.create_task(
        job_queue.run_once(job_send_distribution, run_at, data, job_id)
    )
    return job_id

router = Router()

# ---------------------------------------------------------------------------
@router.message(CommandStart())
@admin_required
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()  # Очищаем состояние
    
    await message.reply(
        "🏠 Главное меню:",
        reply_markup=create_persistent_main_menu()  # ← ИСПОЛЬЗУЕМ НОВУЮ ФУНКЦИЮ
    )
    await state.set_state(Form.STATE_MENU)

@router.message(F.text == "🏠 Главное меню")
@admin_required
async def handle_home_button(message: Message, state: FSMContext):
    """Обрабатывает нажатие кнопки 'Главное меню' из любого состояния"""
    await state.clear()
    
    await message.reply(
        "🏠 Главное меню:",
        reply_markup=create_persistent_main_menu()
    )
    await state.set_state(Form.STATE_MENU)

# ---------------------------------------------------------------------------
# Заменить существующий обработчик handle_menu на этот:
@router.message(lambda message: message.text in [button[0] for button in MENU_BUTTONS])
@admin_required
async def handle_menu(message: Message, state: FSMContext):
    """Обработчик главного меню - работает независимо от состояния"""
    
    # Если состояние не установлено - устанавливаем
    current_state = await state.get_state()
    if current_state is None:
        await state.set_state(Form.STATE_MENU)
    
    text = message.text
    
    if text == "Выбрать воронку":
        await message.answer("🔄 Обновляем воронки…")
        result = await update_amocrm_funnels()
        await ask_audience(message, state, result)
        return

    if text == "Просмотр шаблонов":
        await view_templates(message, state)
        return

    if text == "Просмотреть отчёты":
        await show_reports(message, state)
        return

    if text == "Просмотр запланированных":
        rows = build_scheduled_rows()
        if not rows:
            await message.reply("📭 Запланированных рассылок нет.")
            return

        await message.reply(
            "📅 Запланированные рассылки:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )
        return

    if text == "Просмотр админов":
        rows = build_admin_rows()
        await message.reply(
            "🛡️ Администраторы:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )
        return

    if text == "🏠 Главное меню":
        await message.reply(
            "🏠 Главное меню:",
            reply_markup=create_persistent_main_menu()
        )
        return

    # Если попали сюда - неизвестная команда
    await message.reply("❓ Команда не распознана, выберите опцию из меню.")



# ---------------------------------------------------------------------------
# 6. Хендлеры просмотра отчётов
import pandas as pd

LOG_FILE = 'logs/delivery_logs.csv'

async def show_reports(message: Message, state: FSMContext):
    """
    Показывает список всех отправок, сгруппированных по уникальному funnel ID.
    """
    try:
        df = pd.read_csv(LOG_FILE, parse_dates=['timestamp'])
        if df.empty:
            await message.reply("❌ Нет данных в логах.")
            return

        funnel_stats = {}
        for funnel, group in df.groupby('funnel'):
            min_time = group['timestamp'].min()
            date_label = min_time.strftime('%d.%m.%Y %H:%M')
            total_count = len(group)
            success_count = (group['status'] == 'SUCCESS').sum()
            display_name = f"{date_label} – {success_count}/{total_count}"
            funnel_stats[funnel] = {
                'display_name': display_name,
                'min_time': min_time,
                'total': total_count,
                'success': success_count,
            }

        sorted_funnels = sorted(
            funnel_stats.items(),
            key=lambda x: x[1]['min_time'],
            reverse=True
        )

        buttons = []
        for funnel, stats in sorted_funnels:
            text = stats['display_name']
            callback_stats = f"funnel_rep:{funnel}"
            buttons.append([
                InlineKeyboardButton(text=text,  callback_data=callback_stats),
            ])


        buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="rep_back")])

        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        await message.reply("📊 Отчёты по рассылкам:", reply_markup=keyboard)
        # УДАЛЕНА СТРОКА: await state.set_state(Form.STATE_REPORT_LIST)
    except Exception as e:
        logger.exception(f"Ошибка в show_reports: {e}")
        await message.reply("❌ Ошибка при загрузке отчётов.")




# 2) Обработка клика по отчёту
@router.callback_query(F.data.startswith("funnel_rep:"))
@admin_required
async def cb_funnel_report_detail(query: CallbackQuery, state: FSMContext):
    """
    Показывает детальную статистику по конкретной отправке (funnel).
    """
    try:
        await query.answer()
        funnel = query.data.split(":", 1)[1]

        # Читаем лог
        df = pd.read_csv(LOG_FILE, parse_dates=['timestamp'])
        
        # Фильтруем по funnel
        filtered = df[df['funnel'] == funnel]

        if filtered.empty:
            await query.message.reply("❌ Данные для этой отправки не найдены.")
            return

        # Собираем статистику
        min_time = filtered['timestamp'].min()
        max_time = filtered['timestamp'].max()
        total = len(filtered)
        success = (filtered['status'] == 'SUCCESS').sum()
        failed = total - success
        unique_phones = filtered['phone'].nunique()
        template_id = filtered['template_id'].iloc[0]
        
        # Список телефонов с результатами
        phone_results = []
        for _, row in filtered.iterrows():
            phone = f"+{int(row['phone'])}"  # Конвертируем научную нотацию
            status = "✅" if row['status'] == 'SUCCESS' else "❌"
            phone_results.append(f"{status} {phone}")

        # Определяем тип отправки
        if funnel == '-':
            funnel_display = "Ручная отправка"
        else:
            funnel_display = f"Рассылка {funnel.replace('job_', '')}"

        # Формируем сообщение с детальной статистикой
        duration = (max_time - min_time).total_seconds()
        if duration > 0:
            time_info = f"📅 Период: {min_time.strftime('%d.%m %H:%M:%S')} - {max_time.strftime('%H:%M:%S')}"
        else:
            time_info = f"📅 Время: {min_time.strftime('%d.%m.%Y %H:%M:%S')}"

        headline = (
            f"📅 {min_time.strftime('%d.%m %H:%M')} → "
            f"{max_time.strftime('%H:%M')}  "
            f"({success}/{total})"
        )

        text = (
            f"{headline}\n"
            f"📋 {funnel_display}\n"
            f"🆔 {template_id[:8]}…\n"
            f"✅ Успешно: {success}\n"
            f"❌ Неудач: {failed}\n"
            f"📱 Уникальных номеров: {unique_phones}\n\n"
            f"📞 Детали доставки:\n" + "\n".join(phone_results)
        )


        # Если сообщение слишком длинное, обрезаем список номеров
        if len(text) > 4000:
            phone_results_short = phone_results[:10]
            if len(phone_results) > 10:
                phone_results_short.append(f"... и еще {len(phone_results) - 10} номеров")
            
            text = (
                f"📋 {funnel_display}\n"
                f"{time_info}\n"
                f"🆔 Template ID: {template_id[:8]}...\n"
                f"📊 Всего отправлено: {total}\n"
                f"✅ Успешно: {success}\n"
                f"❌ Неудач: {failed}\n"
                f"📱 Уникальных номеров: {unique_phones}\n\n"
                f"📞 Первые 10 номеров:\n" + "\n".join(phone_results_short)
            )

        # Кнопки навигации
        buttons = [
            [InlineKeyboardButton(text="📥 Скачать JSON",
                                callback_data=f"funnel_json:{funnel}")],
            [InlineKeyboardButton(text="⬅️ К списку отчетов",
                                callback_data="back_to_reports")],
            [InlineKeyboardButton(text="🏠 В главное меню",
                                callback_data="rep_back")]
        ]


        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        await query.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.exception(f"Ошибка в cb_funnel_report_detail: {e}")
        await query.message.reply("❌ Ошибка при получении деталей отчёта.")

# 4. НОВЫЙ обработчик для возврата к списку отчетов (добавить к роутерам)
@router.callback_query(F.data == "back_to_reports")
@admin_required
async def cb_back_to_reports(query: CallbackQuery, state: FSMContext):
    """
    Возвращает к списку отчетов.
    """
    await query.answer()
    # Используем существующую функцию, но вызываем через query.message
    message_like = type('MockMessage', (), {
        'reply': query.message.edit_text
    })()
    await show_reports(message_like, state)

from aiogram.types import FSInputFile

# ---------------------------------------------------------------------------
# 7. Колбэк-хендлер для «📥 Скачать JSON»
@router.callback_query(F.data.startswith("funnel_json:"))
@admin_required
async def cb_download_json(query: CallbackQuery, state: FSMContext) -> None:
    """
    Отправляет компактный JSON-отчёт:
    • агрегаты (успех/неудача, уникальные номера)
    • период начала/конца
    • список номеров + статус (SUCCESS / FAILED)
    """
    await query.answer()

    try:
        funnel_id = query.data.split(":", 1)[1]

        # 1. Загружаем лог
        df = pd.read_csv(LOG_FILE, parse_dates=["timestamp"])
        df_f = df if funnel_id == "-" else df[df["funnel"] == funnel_id]
        if df_f.empty:
            return await query.message.reply("❌ Записей не найдено.")

        # 2. Общие метки времени
        start_ts = df_f["timestamp"].min()
        end_ts   = df_f["timestamp"].max()

        # 3. Итоговая статистика
        total   = len(df_f)
        success = (df_f["status"] == "SUCCESS").sum()
        failed  = total - success
        uniq    = df_f["phone"].nunique()

        # 4. Формируем сокращённую таблицу номеров
        phones_json = (
            df_f[["phone", "status"]]
            .assign(phone=lambda x: "+" + x["phone"].astype(str))  # приводим к +79…
            .to_dict(orient="records")
        )

        payload = {
            "funnel": funnel_id,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "period": {
                "start": start_ts.strftime("%Y-%m-%dT%H:%M:%S"),
                "end":   end_ts.strftime("%Y-%m-%dT%H:%M:%S")
            },
            "summary": {
                "total": int(total),
                "success": int(success),
                "failed": int(failed),
                "unique_phones": int(uniq)
            },
            "phones": phones_json
        }

        # 5. Записываем во временный файл
        filename = f"{funnel_id or 'manual'}_short_{uuid.uuid4().hex[:6]}.json"
        tmp_path = TEMP_CONTACTS_DIR / filename
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), "utf-8")

        # 6. Отправляем
        await query.message.reply_document(
            document=FSInputFile(tmp_path, filename=filename),
            caption="📄JSON-отчёт"
        )

        # 7. Удаляем через 10 мин
        asyncio.create_task(_auto_cleanup(tmp_path))

    except Exception as e:
        logger.exception("Ошибка экспорта JSON: %s", e)
        await query.message.reply("❌ Не удалось сформировать файл.")

async def _auto_cleanup(path: Path, delay: int = 600):
    await asyncio.sleep(delay)
    try:
        path.unlink(missing_ok=True)
    except Exception:
        logger.warning("Не смог удалить %s", path)




# 3) Колбэк "назад" из меню отчётов
@router.callback_query(F.data == "rep_back")
@admin_required
async def cb_report_back(query: CallbackQuery, state: FSMContext):
    await query.answer()
    await query.message.edit_text("🏠 Главное меню.")
    await state.set_state(Form.STATE_MENU)

# ---------------------------------------------------------------------------
async def ask_audience(
    message: Message | CallbackQuery,
    state: FSMContext,
    update_result: str | None = None,
):
    snap_path = AMOCRM_DIR / "funnels.json"
    if not snap_path.exists():
        await (
            message.answer
            if isinstance(message, Message)
            else message.message.answer
        )("❌ Нет файла funnels.json – нажмите ещё раз «Просмотр шаблонов».")
        return

    snap = json.loads(snap_path.read_text("utf-8"))
    buttons = [
        [InlineKeyboardButton(text="👥 Все воронки", callback_data="aud:all")]
    ]

    funnel_map = {}
    for idx, item in enumerate(snap["funnels"]):
        fid = f"f{idx}"
        funnel_map[fid] = item["file"]
        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"📂 {item['name']}", callback_data=f"aud:{fid}"
                )
            ]
        )

    text = (
        f"{update_result}\n\n" if update_result else ""
    ) + "🎯 Выберите аудиторию:"

    await (
        message.answer
        if isinstance(message, Message)
        else message.message.edit_text
    )(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

    await state.update_data(funnel_map=funnel_map)
    await state.set_state(Form.STATE_AUDIENCE)

# ---------------------------------------------------------------------------
async def fetch_templates(prefix: str = "view_tpl"):
    """Загружает шаблоны из локального JSON файла"""
    try:
        if not TEMPLATES_FILE.exists():
            # Создаем файл с примером шаблонов
            default_templates = [
                {
                    "id": "greeting", 
                    "name": "Базовый",
                    "content": "Здравствуйте, {name}! {message}"
                }
            ]
            TEMPLATES_FILE.write_text(
                json.dumps(default_templates, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        
        templates = json.loads(TEMPLATES_FILE.read_text(encoding="utf-8"))
        
        tpl_map: dict[str, dict] = {}
        buttons: list[list[InlineKeyboardButton]] = []
        
        for idx, tpl in enumerate(templates):
            tid = f"t{idx}"
            tpl_map[tid] = tpl
            
            buttons.append([
                InlineKeyboardButton(
                    text=tpl["name"],
                    callback_data=f"{prefix}:{tid}"
                )
            ])
        logger.info("Загружено шаблонов: %d", len(templates))

        return templates, tpl_map, buttons
        
    except Exception as e:
        logger.exception("Ошибка при загрузке шаблонов")
        return [], {}, []

# ---------------------------------------------------------------------------
async def view_templates(message: Message, state: FSMContext):
    try:
        _, tpl_map, buttons = await fetch_templates(prefix="view_tpl")
    except Exception:
        logger.exception("Ошибка при получении шаблонов")
        await message.reply("❌ Не удалось получить список шаблонов.")
        return

    buttons.append([InlineKeyboardButton(text="⬅️ В меню", callback_data="view_back")])
    await message.reply(
        "📋 Доступные шаблоны:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )
    await state.update_data(view_tpl_map=tpl_map)
    # УДАЛЕНА СТРОКА: await state.set_state(Form.STATE_TEMPLATE_VIEW)



@router.callback_query(F.data == "view_back")
@admin_required
async def cb_view_back(query: CallbackQuery, state: FSMContext):
    await query.answer()
    await query.message.edit_text("🏠 Главное меню.")
    await state.set_state(Form.STATE_MENU)

# Замените обработчик cb_view_tpl (удалите строку с set_state в конце)
@router.callback_query(F.data.startswith("view_tpl:"))
@admin_required
async def cb_view_tpl(query: CallbackQuery, state: FSMContext):
    await query.answer()
    tpl_id = query.data.split(":", 1)[1]
    data = await state.get_data()
    tpl = data.get("view_tpl_map", {}).get(tpl_id)
    if not tpl:
        await query.message.reply("❌ Шаблон не найден.")
        return

    body = tpl.get("content", "")
    raw_meta = tpl.get("meta") or "{}"
    try:
        meta = json.loads(raw_meta) if isinstance(raw_meta, str) else raw_meta
    except json.JSONDecodeError:
        meta = {}
    
    example = "Пример: " + body.replace("{name}", "Иван").replace("{message}", "тестовое сообщение")
    preview = (
        f"📋 Шаблон:\n{body}\n\n📝 Пример:\n{example}"
        if example
        else f"📋 Шаблон:\n{body}"
    )
    
    await query.message.edit_text(
        preview,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="view_back")],
                [InlineKeyboardButton(text="🏠 Главное меню", callback_data="to_main_menu")]
            ]
        ),
    )
    # УДАЛЕНА СТРОКА: await state.set_state(Form.STATE_TEMPLATE_VIEW)



# ---------------------------------------------------------------------------

def write_error_with_phone_check(lead_id, lead_name, phone, contact_name):
    """Простая проверка: если номер уже есть в файле - не записываем"""
    error_file = 'logs/Error_numbers.csv'
    
    # Читаем существующие номера телефонов
    existing_phones = set()
    try:
        if os.path.exists(error_file) and os.path.getsize(error_file) > 0:
            with open(error_file, mode='r', encoding='utf-8') as f:
                reader = csv.reader(f)
                next(reader, None)  # пропускаем заголовок
                for row in reader:
                    if len(row) >= 3:  # проверяем что есть колонка phone (3-я колонка)
                        existing_phones.add(row[2])
    except Exception:
        pass  # если не можем прочитать, продолжаем
    
    # Если номер уже есть - не записываем
    if str(phone) in existing_phones:
        return False  # номер уже существует, не записали
    
    # Записываем в файл только если номера еще нет
    with open(error_file, mode='a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([lead_id, lead_name, phone, contact_name])
    
    return True  # номер записан




# 1) Обработчик выбора аудитории: сохраняем список словарей {"phone", "name"}
@router.callback_query(F.data.startswith("aud:"))
@admin_required
async def cb_audience(query: CallbackQuery, state: FSMContext):
    await query.answer()

    # Удаляем все JSON, кроме funnels.json
    for f in AMOCRM_DIR.glob("*.json"):
        if f.name != "funnels.json":
            try:
                f.unlink()
            except Exception as e:
                logger.warning("Не удалось удалить старый файл %s: %s", f, e)

    # Если "Все воронки"
    if query.data == "aud:all":
        contacts = []
        for file in AMOCRM_DIR.glob("*.json"):
            if file.name == "funnels.json":
                continue
            try:
                data = json.loads(file.read_text(encoding="utf-8"))
                if data and isinstance(data[0], str):
                    contacts.extend([{"phone": p, "name": "Клиент"} for p in data])
                else:
                    contacts.extend(data)
            except Exception:
                continue

        tmp = TEMP_CONTACTS_DIR / f"all_contacts_{uuid.uuid4().hex[:8]}.json"
        tmp.write_text(json.dumps(contacts, ensure_ascii=False), encoding="utf-8")
        await state.update_data(contacts=str(tmp))

        cnt = len(contacts)
        min_secs = 40 * cnt
        max_secs = 345 * cnt
        min_hms = str(timedelta(seconds=min_secs))
        max_hms = str(timedelta(seconds=max_secs))

        await query.message.edit_text(
            f"📊 Всего контактов: {cnt}\n"
            f"⏳ Оценка длительности рассылки: от {min_hms} до {max_hms}\n"
            "⚠️ Продолжить?",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="✅ Да", callback_data="aud_all:yes")],
                    [InlineKeyboardButton(text="⬅️ Отмена", callback_data="aud_all:no")],
                ]
            ),
        )
        return

    # Если конкретная воронка
    if query.data.startswith("aud:f"):
        data_state = await state.get_data()
        funnel_map = data_state.get("funnel_map", {})
        fid = query.data.split(":", 1)[1]
        file_name = funnel_map.get(fid)
        if not file_name:
            await query.message.answer("❌ Не удалось определить файл статуса.")
            return

        snap_path = AMOCRM_DIR / "funnels.json"
        if not snap_path.exists():
            await query.message.answer("❌ Файл funnels.json не найден.")
            return
        snap = json.loads(snap_path.read_text("utf-8"))

        status_info = next((f for f in snap["funnels"] if f["file"] == file_name), None)
        if not status_info:
            await query.message.answer("❌ Информация о статусе не найдена.")
            return

        status_name = status_info["name"]
        pipeline_id = status_info["pipeline_id"]
        status_id = status_info["status_id"]
        local = AMOCRM_DIR / file_name

        if not local.exists():
            await query.message.edit_text("⏳ Скачиваю контакты…")
            try:
                leads = mgr.get_leads(pipeline_id, status_id)
                if not leads:
                    await query.message.answer(f"❌ В статусе '{status_name}' сделок нет.")
                    return

                cids = [c["id"] for l in leads for c in l["_embedded"]["contacts"]]
                contacts_raw = mgr.get_contacts_bulk(cids)

                contacts_data = []
                for lead in leads:
                    for c in lead["_embedded"]["contacts"]:
                        co = contacts_raw.get(c["id"], {})
                        phone_raw = mgr.extract_phone(co.get("custom_fields_values", []))
                        name = co.get("name", "") or "Клиент"
                        normalized = mgr.normalize_phone(phone_raw)
                        if normalized:
                            contacts_data.append({"phone": normalized, "name": name})
                        else:
                            write_error_with_phone_check(lead["id"], lead["name"], phone_raw, name)

                # Уникализация
                seen = set()
                unique_contacts = []
                for ct in contacts_data:
                    if ct["phone"] not in seen:
                        seen.add(ct["phone"])
                        unique_contacts.append(ct)

                local.write_text(json.dumps(unique_contacts, ensure_ascii=False), "utf-8")
            except Exception as e:
                await query.message.answer(f"❌ Ошибка при загрузке контактов: {e}")
                return

        contacts = json.loads(local.read_text("utf-8"))
        tmp = TEMP_CONTACTS_DIR / f"{Path(file_name).stem}_{uuid.uuid4().hex[:8]}.json"
        tmp.write_text(json.dumps(contacts, ensure_ascii=False), "utf-8")
        await state.update_data(contacts=str(tmp))

        cnt = len(contacts)
        min_secs = 40 * cnt
        max_secs = 345 * cnt
        min_hms = str(timedelta(seconds=min_secs))
        max_hms = str(timedelta(seconds=max_secs))

        await query.message.edit_text(
            f"✅ Статус: {status_name}\n"
            f"📊 Контактов: {cnt}\n"
            f"⏳ Оценка длительности рассылки(часы, минуты, секунды): от {min_hms} до {max_hms}\n"
            "⚠️ Продолжить?",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="✅ Да", callback_data="aud_f_yes")],
                    [InlineKeyboardButton(text="⬅️ Отмена", callback_data="aud_f_no")],
                ]
            ),
        )
        return

# ---------------------------------------------------------------------------
# выбор шаблона после аудитории
async def send_templates_list(where: Message | CallbackQuery, state: FSMContext):
    try:
        _, tpl_map, buttons = await fetch_templates(prefix="tpl_preview")
    except Exception as e:
        logger.exception(f"Ошибка при получении шаблонов: {e}")
        await (
            where.answer if isinstance(where, Message) else where.message.reply
        )("❌ Не удалось получить список шаблонов.")
        return

    await (
        where.answer if isinstance(where, Message) else where.message.edit_text
    )(
        "📋 Выберите шаблон для рассылки:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )

    # ключ, который ждёт cb_tpl_preview
    await state.update_data(templates_list=tpl_map)
    await state.set_state(Form.STATE_TEMPLATE_CHOOSE)

@router.callback_query(F.data == "aud_f_yes")
@admin_required
async def cb_aud_f_yes(query: CallbackQuery, state: FSMContext):
    await query.answer()
    await send_templates_list(query, state)

@router.callback_query(F.data == "aud_f_no")
@admin_required
async def cb_aud_f_no(query: CallbackQuery, state: FSMContext):
    await query.answer()
    await query.message.edit_text("❌ Действие отменено.")
    await state.set_state(Form.STATE_MENU)

# ---------------------------------------------------------------------------
# Шаблоны – работа с выбранным шаблоном
@router.callback_query(F.data.startswith("tpl_preview:"))
@admin_required
async def cb_tpl_preview(query: CallbackQuery, state: FSMContext):
    await query.answer()
    tpl_id = query.data.split(":", 1)[1]
    data = await state.get_data()
    tpl = data.get("templates_list", {}).get(tpl_id)
    if not tpl:
        await query.message.reply("❌ Шаблон не найден, попробуйте снова.")
        await state.set_state(Form.STATE_MENU)
        return

    body = tpl.get("content", "")
    raw_meta = tpl.get("meta") or "{}"
    try:
        meta = json.loads(raw_meta) if isinstance(raw_meta, str) else raw_meta
    except json.JSONDecodeError:
        meta = {}

    example = meta.get("example", "")
    preview = (
        f"📋 Шаблон:\n{body}\n\n📝 Пример:\n{example}"
        if example
        else f"📋 Шаблон:\n{body}"
    )

    await state.update_data(tpl_selected=tpl_id)

    await query.message.edit_text(
        preview,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="✅ Продолжить", callback_data="tpl_ok"
                    ),
                    InlineKeyboardButton(
                        text="❌ Отмена", callback_data="tpl_cancel"
                    ),
                ]
            ],
        ),
    )
    await state.set_state(Form.STATE_TEMPLATE_CONFIRM)

# 1) В cb_tpl_confirm: сразу переходим к вводу поля "2"

@router.callback_query(F.data.in_(["tpl_ok", "tpl_cancel"]))
@admin_required
async def cb_tpl_confirm(query: CallbackQuery, state: FSMContext):
    await query.answer()

    if query.data == "tpl_cancel":
        await query.message.edit_text("❌ Действие отменено.")
        await state.set_state(Form.STATE_MENU)
        return

    data = await state.get_data()
    tpl = data.get("templates_list", {}).get(data.get("tpl_selected"))
    if not tpl:
        await query.message.reply("❌ Шаблон не найден.")
        await state.set_state(Form.STATE_MENU)
        return

    raw_meta = tpl.get("meta") or "{}"
    try:
        meta = json.loads(raw_meta) if isinstance(raw_meta, str) else raw_meta
    except json.JSONDecodeError:
        meta = {}

    example = meta.get("example", "")

    # Сохраняем выбранный шаблон в state
    await state.update_data(
        chosen_tpl_id = tpl.get("id") or tpl.get("templateId"),
        chosen_tpl_lang = tpl.get("language") or tpl.get("lang") or "ru",
        new_field2 = example
    )

    # Спрашиваем про фото перед полем сообщения
    await query.message.edit_text(
        "📸 Хотите добавить фото к рассылке?",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="📸 Добавить фото", callback_data="add_photo:yes")],
                [InlineKeyboardButton(text="📝 Без фото", callback_data="add_photo:no")],
            ]
        ),
    )
    await state.set_state(Form.STATE_PHOTO_UPLOAD)

@router.callback_query(F.data.startswith("add_photo:"))
@admin_required
async def cb_photo_choice(query: CallbackQuery, state: FSMContext):
    await query.answer()
    
    if query.data == "add_photo:no":
        # Без фото — ввод текста
        await query.message.edit_text("✏️ Введите текст для поля {message}:")
        await state.set_state(Form.STATE_TEMPLATE_NEW_2)
        return
    
    # С фото — просим загрузить
    await query.message.edit_text("📸 Отправьте фото для рассылки:")
    await state.update_data(photo_requested=True)
    # Остаёмся в STATE_PHOTO_UPLOAD


# 5. Обработка загруженного фото
@router.message(Form.STATE_PHOTO_UPLOAD, F.photo)
@admin_required
async def handle_photo_upload(message: Message, state: FSMContext):
    """Обработка загруженного фото"""
    try:
        photo = message.photo[-1]
        await message.bot.get_file(photo.file_id)
        await state.update_data(
            photo_file_id=photo.file_id,
            photo_file_unique_id=photo.file_unique_id
        )
        await message.reply("✅ Фото загружено! Теперь введите текст для поля {message}:")
        await state.set_state(Form.STATE_TEMPLATE_NEW_2)
    except Exception as e:
        logger.exception(f"Ошибка при загрузке фото: {e}")
        await message.reply(
            "❌ Ошибка при загрузке фото. Попробуйте ещё раз или продолжите без фото.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="📝 Продолжить без фото", callback_data="add_photo:no")]
                ]
            )
        )


# 6. Обработка не-фото в состоянии загрузки фото
@router.message(Form.STATE_PHOTO_UPLOAD)
@admin_required  
async def handle_non_photo_in_photo_state(message: Message, state: FSMContext):
    """Обработка не-фото сообщений в состоянии загрузки фото"""
    await message.reply(
        "📸 Пожалуйста, отправьте фото или выберите 'Продолжить без фото'",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="📝 Продолжить без фото", callback_data="add_photo:no")]
            ]
        )
    )


@router.message(Form.STATE_TEMPLATE_NEW_1)
@admin_required
async def new_tpl_field1(message: Message, state: FSMContext):
    text = message.text.strip()
    data = await state.get_data()
    new_data = data.get("new", {"1": "", "2": ""})
    if text:
        new_data["1"] = text

    await state.update_data(new=new_data)

    await message.reply(
        f"✏️ Введите текст для поля {{message}}:"
    )
    await state.set_state(Form.STATE_TEMPLATE_NEW_2)

# 3) Обработка ввода поля 2 (существующая функция new_tpl_field2), без изменений:

@router.message(Form.STATE_TEMPLATE_NEW_2)
@admin_required
async def new_tpl_field2(message: Message, state: FSMContext):
    # Проверяем наличие текста
    if not message.text:
        await message.reply("❌ Пожалуйста, отправьте текстовое сообщение.")
        return
    
    text = message.text.strip()
    
    # Используем новое состояние new_field2
    data = await state.get_data()
    field2 = data.get("new_field2", "")
    
    if text:
        field2 = text
    
    # Сохраняем единственное поле
    MAIN_DATA.write_text(
        json.dumps({"2": field2}, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    
    await message.reply(f"✅ Поле message установлено: «{field2}»")
    
    # Дальше — выбор времени и подтверждение рассылки
    buttons = [
        [InlineKeyboardButton(text="⚡ Сразу отправить", callback_data="time:now")],
        [InlineKeyboardButton(text="⏰ Указать дату/время", callback_data="time:input")],
    ]
    
    await message.reply(
        "⏰ Когда отправить рассылку?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )
    
    await state.set_state(Form.STATE_TIME_CHOOSE)



# ---------------------------------------------------------------------------
@router.callback_query(F.data.startswith("time:"))
@admin_required
async def cb_time_choose(query: CallbackQuery, state: FSMContext):
    await query.answer()
    if query.data.endswith("now"):
        # Сразу – сохраняем run_at и дефолтный диапазон
        await state.update_data(
            run_at=now_tz().isoformat(),
            day_from="00:00",
            day_until="23:59"
        )
        return await confirm_distribution(query.message, state)

    # Если выбрано указать дату/время
    await query.message.reply(
        "📅 Введите дату и время в формате DD.MM.YYYY HH:MM",
        reply_markup=ReplyKeyboardRemove(),
    )
    await state.set_state(Form.STATE_TIME_INPUT)



@router.message(Form.STATE_TIME_INPUT)
@admin_required
async def time_input(message: Message, state: FSMContext):
    dt = parse_datetime(message.text)
    if not dt or dt < now_tz():
        return await message.reply("❌ Некорректная или прошедшая дата, попробуйте снова.")
    await state.update_data(run_at=dt.isoformat())
    # Переходим к вводу диапазона
    await ask_time_range(message, state)


async def ask_time_range(where: Message, state: FSMContext):
    await where.reply(
        "🌓 Укажите с какого по какой период времени будет происходить рассылка формате HH:MM–HH:MM (рекомендуемо с <code>08:00–22:00</code>):",
        reply_markup=ReplyKeyboardRemove(),
    )
    await state.set_state(Form.STATE_TIME_RANGE)

@router.message(Form.STATE_TIME_RANGE)
@admin_required
async def handle_time_range(message: Message, state: FSMContext):
    m = re.match(r"^(\d{2}:\d{2})\s*[–-]\s*(\d{2}:\d{2})$", message.text.strip())
    if not m:
        return await message.reply("❌ Формат HH:MM–HH:MM, попробуйте ещё раз.")
    day_from, day_until = m.groups()
    if datetime.strptime(day_from, '%H:%M') >= datetime.strptime(day_until, '%H:%M'):
        return await message.reply("❌ Начало должно быть раньше конца.")
    await state.update_data(day_from=day_from, day_until=day_until)
    await confirm_distribution(message, state)



async def confirm_distribution(message: Message, state: FSMContext):
    preview = render_message_main()
    data = await state.get_data()
    run_at = datetime.fromisoformat(data["run_at"])
    day_from = data["day_from"]
    day_until = data["day_until"]
    
    # Информация о выбранном этапе
    stage_info = ""
    contacts_file = data.get("contacts", "")
    if contacts_file:
        file_name = Path(contacts_file).stem
        if "all_contacts" not in file_name:
            snap_path = AMOCRM_DIR / "funnels.json"
            if snap_path.exists():
                try:
                    snap = json.loads(snap_path.read_text("utf-8"))
                    for funnel in snap["funnels"]:
                        if file_name in funnel["file"]:
                            stage_info = f"\n📊 Этап: {funnel['name']}"
                            break
                except Exception:
                    pass

    when = "сейчас" if run_at < now_tz() + timedelta(seconds=30) else fmt_local(run_at)
    await message.reply(
        f"📄 Сообщение: Здравствуйте [name]! {preview}\n"
        f"⏰ Старт: {when}\n"
        f"🌗 Диапазон: {day_from} – {day_until}{stage_info}",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text='✅ Подтвердить', callback_data='confirm:yes')],
                [InlineKeyboardButton(text='❌ Отмена', callback_data='confirm:no')],
            ]
        ),
    )
    await state.set_state(Form.STATE_CONFIRM)


@router.callback_query(F.data.startswith("confirm:"))
@admin_required
async def cb_confirm(query: CallbackQuery, state: FSMContext):
    await query.answer()
    # correctly get_data()
    data = await state.get_data()

    # Проверяем, что аудитория выбрана
    if "contacts" not in data:
        await query.message.reply("❌ Сначала выберите аудиторию.")
        await state.set_state(Form.STATE_AUDIENCE)
        return

    # Отмена
    if query.data.endswith("no"):
        await query.message.edit_text("❌ Действие отменено.")
        await state.set_state(Form.STATE_MENU)
        return

    # Получаем все необ
    # ходимые поля из state
    run_at_iso    = data.get("run_at")
    day_from      = data.get("day_from", "00:00")
    day_until     = data.get("day_until", "23:59")
    contacts_file = Path(data["contacts"])
    template_id   = data.get("chosen_tpl_id")
    template_lang = data.get("chosen_tpl_lang", "ru")

    if not run_at_iso or not template_id:
        await query.message.reply("❌ Не удалось получить время или шаблон. Повторите заново.")
        await state.set_state(Form.STATE_MENU)
        return

    run_at = datetime.fromisoformat(run_at_iso)

    # Планируем задачу с учётом диапазона
    job_id = schedule_job(
        run_at,
        contacts_file,
        template_id,
        template_lang,
        day_from=day_from,
        day_until=day_until,
        photo_file_id=data.get("photo_file_id")
    )

    # Форматируем время для пользователя
    when = (
        "сразу"
        if run_at < now_tz() + timedelta(seconds=30)
        else fmt_local(run_at)
    )

    # Отправляем финальное сообщение
    # Отправляем финальное сообщение с кнопками главного меню
# Отправляем финальное сообщение
    await query.message.edit_text(
        f"✅ Рассылка запланирована ({job_id}), время: {when}."
    )

    # Отправляем главное меню
    await query.message.answer(
        "🏠 Главное меню:",
        reply_markup=create_persistent_main_menu()
    )
    await state.set_state(Form.STATE_MENU)





# ---------------------------------------------------------------------------
# 3) Подтверждение рассылки по всем воронкам после выбора "Да"
@router.callback_query(F.data.startswith("aud_all:"))
@admin_required
async def cb_aud_all_confirm(query: CallbackQuery, state: FSMContext):
    await query.answer()
    if query.data == "aud_all:no":
        await query.message.edit_text("❌ Действие отменено.")
        await state.set_state(Form.STATE_MENU)
        return
    # Переходим к выбору шаблона с уже записанным state["contacts"]
    await send_templates_list(query, state)


# ---------------------------------------------------------------------------
@router.callback_query(F.data.startswith("job_detail:"))
@admin_required
async def cb_job_detail(query: CallbackQuery, state: FSMContext):
    await query.answer()
    job_id = query.data.split(":", 1)[1]
    jobs = scheduled_store.read()
    job = next((j for j in jobs if j["job_id"] == job_id), None)
    if not job:
        await query.message.reply("❌ Задача не найдена.")
        return

    run_at = datetime.fromisoformat(job["run_at"])
    when = fmt_local(run_at)

    try:
        contacts_count = len(
            json.loads(Path(job["contacts"]).read_text(encoding="utf-8"))
        )
    except Exception:
        contacts_count = "неизвестно"

    buttons = [
        [
            InlineKeyboardButton(
                text="🗑️ Удалить", callback_data=f"job_delete:{job_id}"
            )
        ],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="job_cancel")],
    ]

    await query.message.edit_text(
        f"📅 Запланированная рассылка:\n"
        f"🕒 Время: {when}\n"
        f"👥 Контактов: {contacts_count}\n"
        f"🆔 ID: {job_id}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )

@router.callback_query(F.data.startswith("job_delete:"))
@admin_required
async def cb_job_delete(query: CallbackQuery, state: FSMContext):
    await query.answer()
    job_id = query.data.split(":", 1)[1]
    scheduled_store.remove(lambda x: x["job_id"] == job_id)
    
    job_queue.jobs = [
        j
        for j in job_queue.jobs
        if j.get("data", {}).get("job_id") != job_id
    ]
    
    await query.message.edit_text(f"✅ Задача {job_id} удалена.")
    await state.set_state(Form.STATE_MENU)

@router.callback_query(F.data == "job_cancel")
@admin_required
async def cb_job_cancel(query: CallbackQuery, state: FSMContext):
    await query.answer()
    await query.message.edit_text("❌ Действие отменено.")
    await state.set_state(Form.STATE_MENU)

# ---------------------------------------------------------------------------
@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.reply(
        "❌ Действие отменено.", reply_markup=ReplyKeyboardRemove()
    )

@router.message(Command("setup"))
async def cmd_setup(message: Message, state: FSMContext):
    """Добавление первого админа"""
    user_id = message.from_user.id
    if not admins_store.read():
        admins_store.append(user_id)
        await message.reply(f"✅ Вы добавлены как первый админ: {user_id}")
    else:
        await message.reply("❌ Админы уже настроены")

async def warmup_amocrm():
    global mgr
    try:
        mgr = await asyncio.to_thread(AmoCRMCategoryManager) # не блокируем loop
        logger.info("✅ AmoCRM готов")
    except Exception as e:
        mgr = None
        logger.error("⚠️ AmoCRM недоступен: %s", e)
#--------------


# Обработчики для управления админами

@router.callback_query(F.data == "adm_add")
@admin_required
async def cb_admin_add(query: CallbackQuery, state: FSMContext):
    """Начало процесса добавления нового админа"""
    await query.answer()
    await query.message.edit_text(
        "👤 Введите ID пользователя, которого хотите добавить в админы:",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_cancel")]
            ]
        )
    )
    await state.set_state(Form.STATE_ADMIN_ADD)

@router.callback_query(F.data.startswith("adm_detail:"))
@admin_required  
async def cb_admin_detail(query: CallbackQuery, state: FSMContext):
    """Показ деталей конкретного админа"""
    await query.answer()
    admin_id = int(query.data.split(":", 1)[1])
    
    buttons = [
        [InlineKeyboardButton(text="🗑️ Удалить", callback_data=f"admin_delete:{admin_id}")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")]
    ]
    
    await query.message.edit_text(
        f"👤 Администратор: {admin_id}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )

@router.message(Form.STATE_ADMIN_ADD)
@admin_required
async def handle_admin_add_input(message: Message, state: FSMContext):
    """Обработка ввода ID нового админа"""
    try:
        user_id = int(message.text.strip())
        admins = admins_store.read()
        
        if user_id in admins:
            await message.reply(
                f"❌ Пользователь {user_id} уже является админом.",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(text="🏠 В главное меню", callback_data="admin_to_menu")]
                    ]
                )
            )
            return
            
        admins_store.append(user_id)
        await message.reply(
            f"✅ Пользователь {user_id} добавлен в админы.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🏠 В главное меню", callback_data="admin_to_menu")]
                ]
            )
        )
        await state.set_state(Form.STATE_MENU)
        
    except ValueError:
        await message.reply(
            "❌ Некорректный ID. Введите числовой ID пользователя:",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_cancel")]
                ]
            )
        )

@router.callback_query(F.data.startswith("admin_delete:"))
@admin_required
async def cb_admin_delete(query: CallbackQuery, state: FSMContext):
    """Удаление админа"""
    await query.answer()
    admin_id = int(query.data.split(":", 1)[1])
    
    # Проверяем, что это не единственный админ
    admins = admins_store.read()
    if len(admins) <= 1:
        await query.message.edit_text(
            "❌ Нельзя удалить единственного администратора.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_back")]
                ]
            )
        )
        return
    
    admins_store.remove(lambda x: x == admin_id)
    await query.message.edit_text(
        f"✅ Администратор {admin_id} удален.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🏠 В главное меню", callback_data="admin_to_menu")]
            ]
        )
    )
    await state.set_state(Form.STATE_MENU)

@router.callback_query(F.data == "admin_cancel")
@admin_required
async def cb_admin_cancel(query: CallbackQuery, state: FSMContext):
    """Отмена операции с админами"""
    await query.answer()
    await query.message.edit_text("❌ Действие отменено.")
    await state.set_state(Form.STATE_MENU)

@router.callback_query(F.data == "admin_back")
@admin_required
async def cb_admin_back(query: CallbackQuery, state: FSMContext):
    """Возврат к списку админов"""
    await query.answer()
    rows = build_admin_rows()
    await query.message.edit_text(
        "🛡️ Администраторы:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
    )

@router.callback_query(F.data == "admin_to_menu")
@admin_required
async def cb_admin_to_menu(query: CallbackQuery, state: FSMContext):
    """Переход в главное меню"""
    await query.answer()
    await query.message.edit_text("🏠 Главное меню.")
    await state.set_state(Form.STATE_MENU)

# ---------------------------------------------------------------------------
# ГЛОБАЛЬНЫЙ ОБРАБОТЧИК для любых состояний: ловит кнопки меню и сбрасывает в главное
@router.message()
@admin_required
async def global_fallback(message: Message, state: FSMContext):
    """
    Обрабатывает сообщения в любом состоянии.
    Если это кнопка меню — сбрасывает состояние и перенаправляет в handle_menu.
    """
    # Получаем текущее состояние
    current_state = await state.get_state()
    
    # Проверяем, является ли текст кнопкой главного меню
    menu_buttons = [button[0] for button in MENU_BUTTONS]  # Предполагаем, что MENU_BUTTONS определено
    is_menu_button = message.text in menu_buttons
    
    # Если это кнопка меню (в любом состоянии)
    if is_menu_button:
        # Сбрасываем состояние на главное меню
        await state.clear()  # Очищаем данные, чтобы не тащить старый flow
        await state.set_state(Form.STATE_MENU)
        
        # Перенаправляем в основной обработчик меню
        await handle_menu(message, state)
        return
    
    # Если состояние не установлено (как в предыдущем решении)
    if current_state is None:
        await message.reply(
            "🏠 Добро пожаловать! Выберите действие из меню:",
            reply_markup=create_persistent_main_menu()
        )
        await state.set_state(Form.STATE_MENU)
        return
    
    # Если сообщение не обработано (fallback для других случаев)
    await message.reply(
        "❓ Команда не распознана. Используйте кнопки меню или нажмите 🏠 Главное меню"
    )

@router.callback_query(F.data == "to_main_menu")
@admin_required
async def cb_to_main_menu(query: CallbackQuery, state: FSMContext):
    await query.answer()
    await state.clear()
    await state.set_state(Form.STATE_MENU)
    await query.message.edit_text(
        "🏠 Главное меню:",
        reply_markup=create_persistent_main_menu()
    )

#--------------------------------------------

async def restore_scheduled_jobs():
    """Восстанавливает запланированные задачи при запуске бота"""
    try:
        jobs = scheduled_store.read()
        current_time = now_tz()
        
        restored_count = 0
        expired_count = 0
        
        for job in jobs[:]:  # Копия списка для безопасного изменения
            try:
                run_at = datetime.fromisoformat(job["run_at"])
                
                # Удаляем просроченные задачи
                if run_at < current_time:
                    scheduled_store.remove(lambda x: x["job_id"] == job["job_id"])
                    expired_count += 1
                    logger.info(f"Удалена просроченная задача: {job['job_id']}")
                    continue
                
                # Восстанавливаем актуальные задачи
                asyncio.create_task(
                    job_queue.run_once(
                        job_send_distribution, 
                        run_at, 
                        job, 
                        job["job_id"]
                    )
                )
                restored_count += 1
                logger.info(f"Восстановлена задача: {job['job_id']} на {fmt_local(run_at)}")
                
            except Exception as e:
                logger.error(f"Ошибка восстановления задачи {job.get('job_id', 'unknown')}: {e}")
        
        logger.info(f"Восстановлено задач: {restored_count}, удалено просроченных: {expired_count}")
        
    except Exception as e:
        logger.exception(f"Ошибка при восстановлении задач: {e}")

# ---------------------------------------------------------------------------
async def main():
    ensure_dirs()
    try:
        token = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))["BOT_TOKEN"]
    except Exception:
        logger.exception("Ошибка чтения token.json")
        raise RuntimeError("Проверьте содержимое token.json")

    # Путь к файлу с ошибочными номерами
    error_file = 'logs/Error_numbers.csv'
    os.makedirs('logs', exist_ok=True)

    # Пишем заголовки, если файл не существует или пуст
    if not os.path.exists(error_file) or os.path.getsize(error_file) == 0:
        with open(error_file, mode='w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['lead_id', 'lead_name', 'phone', 'contact_name'])

    # Заголовки для логов доставки
    HEADERS = ["timestamp", "phone", "template_id", "funnel", "status", "response_info"]
    log_file = 'logs/delivery_logs.csv'
    os.makedirs('logs', exist_ok=True)

    # Пишем заголовки, если файл не существует или пуст
    if not os.path.exists(log_file) or os.path.getsize(log_file) == 0:
        with open(log_file, mode='w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(HEADERS)

    generate_delivery_stats_report(date_from="2025-07-20", date_to="2025-07-21")

    bot = Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)
    dp.include_router(router)

    asyncio.create_task(job_queue.process_jobs())
    asyncio.create_task(warmup_amocrm())
    
    # ← ДОБАВИТЬ ЭТУ СТРОКУ
    await restore_scheduled_jobs()
    
    logger.info("🚀 Бот запущен.")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
