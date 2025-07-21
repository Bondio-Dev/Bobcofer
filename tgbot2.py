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

# ---------------------------------------------------------------------------
# Настройки
BASE_DIR = Path(__file__).parent
TOKEN_FILE = BASE_DIR / "token.json"
CONTACTS_FILE = BASE_DIR / "contacts.json"
MAIN_DATA = BASE_DIR / "data.json"

# API настройки (из bot.py)
API_KEY = "da7uofezaeuxx7pd6yyfnutvsojdjiuk"
SOURCE_NUMBER = "79811090022"
APP_NAME = "BOBCOFFER"
API_URL = "https://api.gupshup.io/sm/api/v1/template/msg"
APP_ID = "8e8e001c-cc0c-4502-b8f5-1682a9628c99"

AMOCRM_DIR = BASE_DIR / "amocrm_contacts"
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
def send_template_sync(dest: str,
                      template_id: str,
                      params: list[str],
                      lang: str = "ru",
                      funnel: str = "") -> tuple[int, str]:
    logging.debug("send_template → dest=%s, tpl_id=%s, params=%s, lang=%s",
                 dest, template_id, params, lang)
    
    payload = {
        "source": SOURCE_NUMBER,
        "destination": dest,
        "template": json.dumps({
            "id": template_id,
            "params": params,
            "languageCode": lang,
        }),
        "src.name": APP_NAME,
    }
    
    headers = {
        "apikey": API_KEY,
        "Content-Type": "application/x-www-form-urlencoded",
    }
    
    try:
        r = requests.post(API_URL, data=payload, headers=headers, timeout=10)
        success = r.status_code == 202
        log_message(dest, success, r.text, template_id, funnel) # передаём funnel
        logging.debug("Gupshup HTTP %s → %s", r.status_code, r.text[:400])
        return r.status_code, r.text
    except Exception as e:
        error_msg = f"Error: {e}"
        log_message(dest, False, error_msg, template_id, funnel)
        logging.exception("⛔ Request failed")
        return 0, error_msg

# ---------------------------------------------------------------------------
# Асинхронная обертка для отправки
async def send_template_async(dest: str,
                             template_id: str,
                             params: list[str],
                             lang: str = "ru",
                             funnel: str = "") -> tuple[int, str]:
    """Асинхронная обертка для send_template_sync"""
    return await asyncio.to_thread(send_template_sync, dest, template_id, params, lang, funnel)

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
]

# ---------------------------------------------------------------------------
# States
class Form(StatesGroup):
    STATE_MENU = State()
    STATE_TEMPLATE_CHOOSE = State()
    STATE_TEMPLATE_CONFIRM = State()
    STATE_TEMPLATE_NEW_1 = State()
    STATE_TEMPLATE_NEW_2 = State()
    STATE_TEMPLATE_VIEW = State()
    STATE_AUDIENCE = State()
    STATE_TIME_CHOOSE = State()
    STATE_TIME_INPUT = State()
    STATE_CONFIRM = State()
    STATE_ADMIN_ADD = State()
    STATE_AMOCRM_INPUT = State()
    STATE_AMOCRM_FILENAME = State()
    STATE_REPORT_LIST = State()
    STATE_REPORT_DETAIL = State()

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
        r = requests.get(
            f"{self.base_url}/leads/pipelines/{pipeline_id}",
            headers=self.headers,
            timeout=20,
        )
        r.raise_for_status()
        return [(s["id"], s["name"]) for s in r.json()["_embedded"]["statuses"]]

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

# глобальная сессия ─ создаём один раз
session: aiohttp.ClientSession | None = None

async def get_session() -> aiohttp.ClientSession:
    global session
    if session is None or session.closed:
        session = aiohttp.ClientSession()
    return session

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


class JsonStore:
    def __init__(self, path: Path):
        self.path = path
        if not self.path.exists():
            self.path.write_text("[]", encoding="utf-8")

    def read(self) -> list:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def write(self, data: list):
        self.path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def append(self, item):
        data = self.read()
        data.append(item)
        self.write(data)

    def remove(self, predicate):
        data = [x for x in self.read() if not predicate(x)]
        self.write(data)

admins_store = JsonStore(BASE_DIR / "admins.json")
scheduled_store = JsonStore(BASE_DIR / "scheduled.json")

def admin_required(func):
    async def wrapper(message_or_query, state: FSMContext, *args, **kwargs):
        user_id = (
            message_or_query.from_user.id
            if isinstance(message_or_query, (Message, CallbackQuery))
            else None
        )
        if user_id not in admins_store.read():
            if isinstance(message_or_query, CallbackQuery):
                await message_or_query.message.reply_text("❌ Доступ запрещён.")
            else:
                await message_or_query.reply("❌ Доступ запрещён.")
            return
        return await func(message_or_query, state)
    return wrapper

def ensure_dirs():
    BASE_DIR.mkdir(exist_ok=True)
    AMOCRM_DIR.mkdir(exist_ok=True)
    if not TOKEN_FILE.exists():
        TOKEN_FILE.write_text('{"BOT_TOKEN": "YOUR_TOKEN_HERE"}', encoding="utf-8")
    if not CONTACTS_FILE.exists():
        CONTACTS_FILE.write_text("[]", encoding="utf-8")
    if not MAIN_DATA.exists():
        MAIN_DATA.write_text('{"1": "", "2": ""}', encoding="utf-8")

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

def build_scheduled_rows():
    jobs = scheduled_store.read()
    return [
        [
            InlineKeyboardButton(
                text=fmt_local(datetime.fromisoformat(j["run_at"])),
                callback_data=f"job_detail:{j['job_id']}",
            )
        ]
        for j in jobs
    ]

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

# ---------------------------------------------------------------------------
# ИЗМЕНЕННАЯ ФУНКЦИЯ: используем прямой вызов вместо subprocess
async def job_send_distribution(context):
    try:
        job = context.data
        contacts_path = Path(job["contacts"])
        if not contacts_path.exists():
            logger.error("Контактный файл %s не найден", contacts_path)
            return

        phones = json.loads(contacts_path.read_text("utf-8"))
        data = json.loads(MAIN_DATA.read_text("utf-8"))
        params = [data["1"], data["2"]]

        # ЗАМЕНА: вместо send_via_bot_py используем прямой вызов send_template_async
        for phone in phones:
            code, resp = await send_template_async(
                dest=phone,
                template_id=job["template_id"],
                params=params,
                lang=job["template_lang"],
                funnel=job["job_id"]  # передаем job_id как funnel
            )
            
            # Логирование для JSON формата (как было в send_via_bot_py)
            log_extra = {
                "template": job["template_id"],
                "funnel": job["job_id"],
                "phone": phone,
                "success": code == 202,
                "err": resp if code != 202 else "",
            }
            
            level = logging.INFO if code == 202 else logging.ERROR
            logger.log(level,
                      "%s → %s", phone,
                      "OK" if code == 202 else f"ERR {code}",
                      extra=log_extra)
            
            await asyncio.sleep(0.5)  # асинхронная пауза

        scheduled_store.remove(lambda x: x["job_id"] == job["job_id"])
        logger.info(
            "Рассылка %s завершена (%d номеров)", job["job_id"], len(phones)
        )

    except Exception:
        logger.exception("Ошибка в job_send_distribution")

def schedule_job(run_at: datetime,
                contacts_file: Path,
                template_id: str,
                template_lang: str) -> str:
    """
    Сохраняет задачу в scheduled.json и регистрирует её в SimpleJobQueue.
    Возвращает сгенерированный job_id.
    """
    job_id = f"job_{uuid.uuid4().hex[:8]}"
    data = {
        "job_id": job_id,
        "run_at": run_at.isoformat(),
        "contacts": str(contacts_file),
        "template_id": template_id,
        "template_lang": template_lang # ← новый ключ
    }
    
    #--- логируем для отладки
    logger.debug(
        "schedule_job → id=%s, run_at=%s, contacts=%s, tpl=%s",
        job_id, run_at, contacts_file, template_id
    )
    
    scheduled_store.append(data)
    # регистрируем задачу в очереди
    asyncio.create_task(
        job_queue.run_once(job_send_distribution, run_at, data, job_id)
    )
    
    return job_id

router = Router()

# ---------------------------------------------------------------------------
@router.message(CommandStart())
@admin_required
async def cmd_start(message: Message, state: FSMContext):
    keyboard = [
        [KeyboardButton(text=row[0])] for row in MENU_BUTTONS
    ]
    await message.reply(
        "🏠 Главное меню:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=keyboard,
            resize_keyboard=True
        ),
    )
    await state.set_state(Form.STATE_MENU)

# ---------------------------------------------------------------------------
@router.message(Form.STATE_MENU)
@admin_required
async def handle_menu(message: Message, state: FSMContext):
    text = message.text
    
    if text == "Выбрать воронку":
        await message.answer("🔄 Обновляем воронки…")
        result = await update_amocrm_funnels()
        await ask_audience(message, state, result)
        return

    if text == "Просмотр шаблонов":
        await view_templates(message, state)
        return

    if text == "Просмотреть отчёты": # <-- Добавляем эту ветку
        await message.answer(generate_delivery_stats_report(date_from="2025-07-20", date_to="2025-07-21")) # <-- Вызываем функцию
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

    # опционально: обрабатывать неизвестные команды
    await message.reply("❓ Команда не распознана, выберите опцию из меню.")

# ---------------------------------------------------------------------------
# 6. Хендлеры просмотра отчётов
import pandas as pd

LOG_FILE = 'logs/delivery_logs.csv'

# 1) Функция показа списка отчётов
async def show_reports(message: Message, state: FSMContext):
    # Читаем CSV в DataFrame
    df = pd.read_csv(LOG_FILE, parse_dates=['timestamp'])
    if df.empty:
        await message.reply("❌ Нет данных в логах.")
        return

    # Извлекаем дату-время (без секунд) и группируем
    df['run_time'] = df['timestamp'].dt.strftime('%Y-%m-%d %H:%M')
    groups = df.groupby(['run_time', 'template_id'], as_index=False).size()

    # Получаем сопоставление template_id → название шаблона
    # Предполагаем, что в state хранится tpl_map из fetch_templates
    data = await state.get_data()
    tpl_map = data.get('view_tpl_map', {})

    # Формируем кнопки
    buttons = []
    for _, row in groups.iterrows():
        rt = row['run_time']
        tid = row['template_id']
        title = tpl_map.get(tid, {}).get('name', tid)
        text = f"{rt} | {title}"
        callback = f"rep:{rt}:{tid}"
        buttons.append([InlineKeyboardButton(text=text, callback_data=callback)])

    # Кнопка "назад"
    buttons.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="rep_back")])

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.reply("📊 Отчёты рассылок:", reply_markup=keyboard)
    await state.set_state(Form.STATE_REPORT_LIST)

# 2) Обработка клика по отчёту
@router.callback_query(F.data.startswith("rep:"))
@admin_required
async def cb_report_detail(query: CallbackQuery, state: FSMContext):
    try:
        await query.answer()
        parts = query.data.split(":", 2)
        if len(parts) != 3:
            await query.message.reply("❌ Некорректные данные отчёта.")
            return

        _, run_time, template_id = parts

        # Читаем лог
        df = pd.read_csv(LOG_FILE, parse_dates=['timestamp'])
        df['run_time'] = df['timestamp'].dt.strftime('%Y-%m-%d %H:%M')

        # Фильтруем по времени и template_id
        filtered = df[(df['run_time'] == run_time) & (df['template_id'] == template_id)]

        if filtered.empty:
            await query.message.reply("❌ Данные для этого периода не найдены.")
            return

        total = len(filtered)
        success = (filtered['status'] == 'SUCCESS').sum()
        failed = total - success

        # Получаем название шаблона
        data = await state.get_data()
        tpl_map = data.get('view_tpl_map', {})
        template_name = "Неизвестный шаблон"
        for tid, tpl in tpl_map.items():
            if tpl.get('id') == template_id or tpl.get('templateId') == template_id:
                template_name = tpl.get('name', tpl.get('templateName', template_id))
                break

        # Отправляем отчёт
        text = (
            f"📅 Время: {run_time}\n"
            f"📝 Шаблон: {template_name}\n"
            f"📊 Всего отправлено: {total}\n"
            f"✅ Успешно: {success}\n"
            f"❌ Неудач: {failed}"
        )

        await query.message.reply(text)

    except Exception as e:
        logger.exception(f"Ошибка в cb_report_detail: {e}")
        await query.message.reply("❌ Ошибка при получении деталей отчёта.")

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
    """
    Возвращает:
    templates – оригинальный список шаблонов из Gupshup
    tpl_map – {id_на_кнопке: объект_шаблона}
    buttons – список рядов InlineKeyboardButton
    """
    sess = await get_session()
    url = f"https://api.gupshup.io/wa/app/{APP_ID}/template"
    headers = {
        "accept": "application/json",
        "apikey": API_KEY,
    }

    async with sess.get(url, headers=headers) as resp:
        if resp.status != 200:
            raise RuntimeError(
                f"Gupshup HTTP {resp.status}: {await resp.text()}"
            )

        data = await resp.json()
        # --- НОВОЕ: поддерживаем обе схемы ответа ---
        templates: list[dict] = data.get("templates") or data.get("data") or []
        # --------------------------------------------

        if not templates:
            logger.warning("Gupshup вернул пустой список шаблонов")
            return [], {}, []

        tpl_map: dict[str, dict] = {}
        buttons: list[list[InlineKeyboardButton]] = []

        for idx, tpl in enumerate(templates):
            tid = f"t{idx}"
            tpl_map[tid] = tpl

            title = (
                tpl.get("name")
                or tpl.get("templateName")
                or tpl.get("elementName") # встречается в новых ответах
                or f"Шаблон {idx+1}"
            )

            buttons.append(
                [InlineKeyboardButton(
                    text=title, # именованный аргумент
                    callback_data=f"{prefix}:{tid}"
                )]
            )

        return templates, tpl_map, buttons

# ---------------------------------------------------------------------------
# список шаблонов из «Главного меню»
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

    await state.update_data(view_tpl_map=tpl_map) # для cb_view_tpl
    await state.set_state(Form.STATE_TEMPLATE_VIEW)

@router.callback_query(F.data == "view_back")
@admin_required
async def cb_view_back(query: CallbackQuery, state: FSMContext):
    await query.answer()
    await query.message.edit_text("🏠 Главное меню.")
    await state.set_state(Form.STATE_MENU)

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

    body = tpl.get("templateContent") or tpl.get("body") or tpl.get("content", "")
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

    await query.message.edit_text(
        preview,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="⬅️ Назад", callback_data="view_back")]
            ]
        ),
    )
    await state.set_state(Form.STATE_TEMPLATE_VIEW)

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




@router.callback_query(F.data.startswith(("aud:",)))
@admin_required
async def cb_audience(query: CallbackQuery, state: FSMContext):
    await query.answer()
    
    if query.data == "aud:all":
        contacts = []
        for file in AMOCRM_DIR.glob("*.json"):
            if file.name == "funnels.json": # Пропускаем служебный файл
                continue
            try:
                data = json.loads(file.read_text(encoding="utf-8"))
                contacts.extend(data)
            except Exception:
                continue

        tmp = (
            MAIN_DATA.parent
            / f"all_contacts_{uuid.uuid4().hex[:8]}.json"
        )
        tmp.write_text(
            json.dumps(contacts, ensure_ascii=False), encoding="utf-8"
        )
        await state.update_data(contacts=str(tmp))

        await query.message.edit_text(
            f"⚠️ Вы выбрали рассылку по всем статусам ({len(contacts)} шт.). Вы уверены?",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(text="✅ Да", callback_data="aud_all:yes"),
                        InlineKeyboardButton(text="⬅️ Отмена", callback_data="aud_all:no"),
                    ]
                ],
            ),
        )
        return

    if query.data.startswith("aud:f"):
        data_state = await state.get_data()
        funnel_map: dict = data_state.get("funnel_map", {})
        fid = query.data.split(":", 1)[1]
        file_name = funnel_map.get(fid)
        if not file_name:
            await query.message.answer("❌ Не удалось определить файл статуса.")
            return

        # Получаем информацию о статусе из funnels.json
        snap_path = AMOCRM_DIR / "funnels.json"
        if not snap_path.exists():
            await query.message.answer("❌ Файл funnels.json не найден.")
            return

        snap = json.loads(snap_path.read_text("utf-8"))
        status_info = None
        for funnel in snap["funnels"]:
            if funnel["file"] == file_name:
                status_info = funnel
                break

        if not status_info:
            await query.message.answer("❌ Информация о статусе не найдена.")
            return

        local = AMOCRM_DIR / file_name
        status_name = status_info["name"]
        pipeline_id = status_info["pipeline_id"]
        status_id = status_info["status_id"]

        if not local.exists():
            await query.message.answer("⏳ Скачиваю контакты…")
            try:
                leads = mgr.get_leads(pipeline_id, status_id)
                if not leads:
                    await query.message.answer(f"❌ В статусе '{status_name}' сделок нет.")
                    return

                cids = [
                    c["id"] for l in leads for c in l["_embedded"]["contacts"]
                ]
                contacts_raw = mgr.get_contacts_bulk(cids)
                phones: list[str] = []

                for lead in leads:
                    for c in lead["_embedded"]["contacts"]:
                        co = contacts_raw.get(c["id"], {})
                        phone = mgr.extract_phone(
                            co.get("custom_fields_values", [])
                        )
                        if phone:
                            contact_name = co.get("name", "")
                        normalized = mgr.normalize_phone(phone)
                        if normalized:
                            phones.append(normalized)
                            
                        else:
                            write_error_with_phone_check(lead['id'], lead['name'], phone, contact_name)

                phones = list(dict.fromkeys(phones))
                
                local.write_text(
                    json.dumps(phones, ensure_ascii=False), "utf-8"
                )

            except Exception as e:
                await query.message.answer(f"❌ Ошибка при загрузке контактов: {e}")
                return

        contacts = json.loads(local.read_text("utf-8"))
        tmp = (
            MAIN_DATA.parent
            / f"{Path(file_name).stem}_{uuid.uuid4().hex[:8]}.json"
        )
        tmp.write_text(json.dumps(contacts, ensure_ascii=False), "utf-8")
        await state.update_data(contacts=str(tmp))

        await query.message.edit_text(
            f"✅ Статус: {status_name}\n"
            f"📊 Загружено {len(contacts)} контактов.\n"
            f"⚠️ Продолжить?",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(text="✅ Да", callback_data="aud_f_yes"),
                        InlineKeyboardButton(text="⬅️ Отмена", callback_data="aud_f_no"),
                    ]
                ],
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

    body = tpl.get("templateContent") or tpl.get("body") or tpl.get("content", "")
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

@router.callback_query(F.data.in_(["tpl_ok", "tpl_cancel"]))
@admin_required
async def cb_tpl_confirm(query: CallbackQuery, state: FSMContext):
    await query.answer()

    if query.data == "tpl_cancel":
        await query.message.edit_text("❌ Действие отменено.")
        await state.set_state(Form.STATE_MENU)
        return

    data = await state.get_data()
    tpl_id = data.get("tpl_selected")
    tpl = data.get("templates_list", {}).get(tpl_id)
    if not tpl:
        await query.message.reply("❌ Шаблон не найден.")
        await state.set_state(Form.STATE_MENU)
        return

    body = tpl.get("templateContent") or tpl.get("body") or tpl.get("content", "")
    raw_meta = tpl.get("meta") or "{}"
    try:
        meta = json.loads(raw_meta) if isinstance(raw_meta, str) else raw_meta
    except json.JSONDecodeError:
        meta = {}

    example = meta.get("example", "")
    await state.update_data(new={"1": body, "2": example})
    await state.update_data(chosen_tpl_id = tpl.get("id") or tpl.get("templateId"),
                           chosen_tpl_lang = tpl.get("language") or tpl.get("lang") or "ru")

    await query.message.edit_text(
        f"✏️ Введите текст для поля {{1}} (по умолчанию «{body}»):"
    )
    await state.set_state(Form.STATE_TEMPLATE_NEW_1)

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
        f"✏️ Введите текст для поля {{2}} (по умолчанию «{new_data['2']}»):"
    )
    await state.set_state(Form.STATE_TEMPLATE_NEW_2)

@router.message(Form.STATE_TEMPLATE_NEW_2)
@admin_required
async def new_tpl_field2(message: Message, state: FSMContext):
    text = message.text.strip()
    data = await state.get_data()
    new_data = data.get("new", {"1": "", "2": ""})
    if text:
        new_data["2"] = text

    MAIN_DATA.write_text(
        json.dumps(new_data, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    await message.reply(
        f"✅ Поля установлены:\n"
        f"{{1}} = «{new_data['1']}»\n"
        f"{{2}} = «{new_data['2']}»"
    )

    buttons = [
        [
            InlineKeyboardButton(text="⚡ Сразу отправить", callback_data="time:now"),
            InlineKeyboardButton(
                text="⏰ Указать дату/время", callback_data="time:input"
            ),
        ]
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
        min_time = now_tz()
        await state.update_data(run_at=min_time.isoformat())
        await confirm_distribution(query.message, state)
        return

    await query.message.reply(
        "📅 Введите дату и время в формате DD.MM.YYYY HH:MM",
        reply_markup=ReplyKeyboardRemove(),
    )
    await state.set_state(Form.STATE_TIME_INPUT)

@router.message(Form.STATE_TIME_INPUT)
@admin_required
async def time_input(message: Message, state: FSMContext):
    dt = parse_datetime(message.text)
    min_time = now_tz()
    if not dt:
        await message.reply("❌ Некорректная дата/время, попробуйте снова.")
        return

    if dt < min_time:
        await message.reply(
            f"⚠️ Минимальное время отправки: {fmt_local(min_time)}"
        )
        return

    await state.update_data(run_at=dt.isoformat())
    await confirm_distribution(message, state)

async def confirm_distribution(message: Message, state: FSMContext):
    preview = render_message_main()
    data = await state.get_data()
    run_at = datetime.fromisoformat(data["run_at"])

    when = (
        "сейчас"
        if run_at < now_tz() + timedelta(seconds=30)
        else fmt_local(run_at)
    )

    buttons = [
        [
            InlineKeyboardButton(text="✅ Подтвердить", callback_data="confirm:yes"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="confirm:no"),
        ]
    ]

    await message.reply(
        f"📄 Сообщение:\n\n{preview}\n\n⏰ Будет отправлено: {when}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )
    await state.set_state(Form.STATE_CONFIRM)

@router.callback_query(F.data.startswith("confirm:"))
@admin_required
async def cb_confirm(query: CallbackQuery, state: FSMContext):
    await query.answer()
    data = await state.get_data()

    if "contacts" not in data:
        await query.message.reply("❌ Сначала выберите аудиторию.")
        await state.set_state(Form.STATE_AUDIENCE)
        return

    if query.data.endswith("no"):
        await query.message.edit_text("❌ Действие отменено.")
        await state.set_state(Form.STATE_MENU)
        return

    template_id = data["chosen_tpl_id"]
    template_lang = data.get("chosen_tpl_lang", "ru")

    job_id = schedule_job(datetime.fromisoformat(data["run_at"]),
                         Path(data["contacts"]),
                         template_id,
                         template_lang)

    run_at = datetime.fromisoformat(data["run_at"])
    when = (
        "сразу"
        if run_at < now_tz() + timedelta(seconds=30)
        else fmt_local(run_at)
    )

    await query.message.edit_text(
        f"✅ Рассылка запланирована ({job_id}), время: {when}."
    )
    await state.set_state(Form.STATE_MENU)

# ---------------------------------------------------------------------------
@router.callback_query(F.data.startswith("aud_all:"))
@admin_required
async def cb_aud_all_confirm(query: CallbackQuery, state: FSMContext):
    await query.answer()

    if query.data == "aud_all:no":
        await query.message.edit_text("❌ Действие отменено.")
        await state.set_state(Form.STATE_MENU)
        return

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
    asyncio.create_task(warmup_amocrm()) # 👈 новый фон-таск

    logger.info("🚀 Бот запущен.")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
