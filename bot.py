# bot.py — скрипт отправки через Gupshup API с логированием
import json, time, sys, os
import requests
from datetime import datetime
import logging

def setup_logger():
    """Единый DEBUG-лог в файл logs/bot_debug.log"""
    os.makedirs("logs", exist_ok=True)
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[
            logging.FileHandler("logs/bot_debug.log", encoding="utf-8"),
            logging.StreamHandler(sys.stdout)          # видно при локальном запуске
        ]
    )

setup_logger()


API_KEY        = "da7uofezaeuxx7pd6yyfnutvsojdjiuk"
SOURCE_NUMBER  = "79811090022"
APP_NAME       = "BOBCOFFER"
TEMPLATE_ID    = "263ad3ff-a524-4d0f-94f5-b6d1a369f915"
API_URL        = "https://api.gupshup.io/sm/api/v1/template/msg"

# Файл для логов
LOG_FILE = "delivery_logs.txt"

def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def log_message(phone, success, response_text=""):
    """Простое логирование статуса отправки"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status = "SUCCESS" if success else "FAILED"
    
    log_entry = f"{timestamp} | {phone} | {status}"
    if response_text:
        log_entry += f" | {response_text}"
    log_entry += "\n"
    
    # Создаем папку logs если её нет
    os.makedirs("logs", exist_ok=True)
    
    with open(f"logs/{LOG_FILE}", "a", encoding="utf-8") as f:
        f.write(log_entry)

# ---------- замените старые версии функций ----------

def send_template(dest: str,
                  template_id: str,
                  params: list[str],
                  lang: str = "ru") -> tuple[int, str]:
    """
    Отправляет шаблон WhatsApp через Gupshup.
    Возвращает (HTTP-код, тело ответа).
    """
    logging.debug("send_template → dest=%s, tpl_id=%s, params=%s, lang=%s",
                  dest, template_id, params, lang)

    payload = {
        "source": SOURCE_NUMBER,
        "destination": dest,
        "template": json.dumps({
            "id": template_id,
            "params": params,
            "languageCode": lang          # <─ теперь переменная определена
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
        log_message(dest, success, r.text)
        logging.debug("Gupshup HTTP %s → %s", r.status_code, r.text[:400])
        return r.status_code, r.text
    except Exception as e:
        log_message(dest, False, f"Error: {e}")
        logging.exception("⛔ Request failed")
        return 0, f"Error: {e}"


def main():
    """
    • python bot.py <phone> '{"id": "<tpl>", "params": ["1","2"], "lang": "ru"}'
    • без аргументов → массовая рассылка по contacts.json
    """
    # ---------- одиночная отправка ----------
    if len(sys.argv) == 3:
        phone = sys.argv[1]
        info  = json.loads(sys.argv[2])
        code, resp = send_template(
            phone,
            info["id"],
            info["params"],
            info.get("lang", "ru")        # <─ вытаскиваем язык, если передан
        )
        print(f"{phone}: {code} → {resp}")
        sys.exit(0 if code == 202 else 1)

    # ---------- массовый режим (язык = "ru") ----------
    ...



def main():
    """
    Режимы:
      • python bot.py <phone> '{"id": "<tpl_id>", "params": ["1","2"]}'
      • python bot.py            ➜ массовая рассылка contacts.json
    """
    if len(sys.argv) == 3:
        phone = sys.argv[1]
        info  = json.loads(sys.argv[2])     # {"id": ..., "params": [...]}
        code, resp = send_template(phone, info["id"], info["params"])
        print(f"{phone}: {code} → {resp}")
        # возврат 0/1 пригодится tgbot для проверки
        sys.exit(0 if code == 202 else 1)

    # ---------------- массовый режим ----------------
    contacts = load_json("contacts.json")
    data     = load_json("data.json")       # {"id": "...", "1": "...", "2": "..."}
    tpl_id   = data["id"]
    params   = [data["1"], data["2"]]

    total_sent = successful = 0
    logging.info("Start bulk send; contacts=%d, tpl=%s", len(contacts), tpl_id)

    for num in contacts:
        code, _ = send_template(num, tpl_id, params)
        total_sent += 1
        if code == 202:
            successful += 1
        time.sleep(0.5)

    logging.info("Bulk done: %d/%d success", successful, total_sent)


if __name__ == "__main__":
    main()
