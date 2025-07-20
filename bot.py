# bot.py — скрипт отправки через Gupshup API с логированием
import json, time, sys, os
import requests
from datetime import datetime
import logging
import csv

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


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)

# ---------------------------------------------------------------------------
# bot.py – запись в текстовый delivery_logs.txt
# ---------------------------------------------------------------------------
from datetime import datetime


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


# ---------- замените старые версии функций ----------

# bot.py
# ──────────────────────────────────────────────────────────
# bot.py
# ──────────────────────────────────────────────────────────
# ---------------------------------------------------------------------------
# 8. send_template вызывает log_message с template_id
# ---------------------------------------------------------------------------
def send_template(dest: str,
                  template_id: str,
                  params: list[str],
                  lang: str = "ru") -> tuple[int, str]:
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
        log_message(dest, success, r.text, template_id)   # 👈 передаём id шаблона
        logging.debug("Gupshup HTTP %s → %s", r.status_code, r.text[:400])
        return r.status_code, r.text
    except Exception as e:
        log_message(dest, False, f"Error: {e}", template_id)
        logging.exception("⛔ Request failed")
        return 0, f"Error: {e}"



def main():
    """
    • python bot.py <phone> '{"id": "...", "params": ["1","2"], "lang": "ru"}'
    • без аргументов  → массовая рассылка contacts.json
    """
    if len(sys.argv) == 3:                                  # одиночная отправка
        phone = sys.argv[1]
        info  = json.loads(sys.argv[2])
        code, resp = send_template(
            phone,
            info["id"],
            info["params"],
            info.get("lang", "ru")
        )
        print(f"{phone}: {code} → {resp}")
        sys.exit(0 if code == 202 else 1)

    # ---------------- массовый режим (язык = "ru") ----------------
    contacts = load_json("contacts.json")
    data     = load_json("data.json")            # {"id": "...", "1": "...", "2": "..."}
    tpl_id   = data["id"]
    params   = [data["1"], data["2"]]

    total_sent = successful = 0
    logging.info("Start bulk send; contacts=%d, tpl=%s", len(contacts), tpl_id)

    for num in contacts:
        code, _ = send_template(num, tpl_id, params, "ru")
        total_sent += 1
        if code == 202:
            successful += 1
        time.sleep(0.5)

    logging.info("Bulk done: %d/%d success", successful, total_sent)


if __name__ == "__main__":
    main()
