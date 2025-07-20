import pandas as pd
import os
from datetime import datetime
from typing import List, Union, Optional

def generate_delivery_stats_report(
    date_from: Union[str, datetime] = None,
    date_to: Union[str, datetime] = None,
    error_file: str = "logs/Error_numbers.csv",
    log_file: str = "logs/delivery_logs.csv",
    output_dir: str = "logs",
) -> str:
    """
    Генерирует текстовый отчёт по статистике рассылки за указанный интервал дат.

    Аргументы:
        date_from, date_to: начало и конец периода (включая обе даты)
            Если None — берутся все доступные данные.
            Можно передать строку в формате 'YYYY-MM-DD' или datetime.
        error_file, log_file: пути к файлам с ошибками и логами
        output_dir: папка для сохранения отчёта

    Возвращает:
        Путь к файлу с отчётом.
    """
    # --- Подготовка дат ---
    if isinstance(date_from, str):
        date_from = pd.to_datetime(date_from).normalize()
    if isinstance(date_to, str):
        date_to = pd.to_datetime(date_to).normalize() + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
    os.makedirs(output_dir, exist_ok=True)

    # --- Загрузка данных ---
    error_df = pd.read_csv(error_file)
    log_df = pd.read_csv(log_file)

    # --- Фильтрация по дате (если заданы даты) ---
    log_df["timestamp_dt"] = pd.to_datetime(log_df["timestamp"])
    if date_from is not None:
        log_df = log_df[log_df["timestamp_dt"] >= date_from]
    if date_to is not None:
        log_df = log_df[log_df["timestamp_dt"] <= date_to]

    # --- Статистика ---
    sent_total = len(log_df)
    sent_success = len(log_df[log_df["status"] == "SUCCESS"])
    sent_failed = sent_total - sent_success

    # --- Формируем список ошибочных номеров в удобном для чтения виде ---
    error_table = error_df[["lead_name", "phone", "contact_name"]].to_string(index=False, header=True)

    # --- Формируем имя файла для отчёта ---
    date_part = ""
    if date_from is not None and date_to is not None:
        date_part = f"_{date_from.strftime('%Y-%m-%d')}_to_{date_to.strftime('%Y-%m-%d')}"
    elif date_from is not None:
        date_part = f"_from_{date_from.strftime('%Y-%m-%d')}"
    elif date_to is not None:
        date_part = f"_to_{date_to.strftime('%Y-%m-%d')}"
    report_file = os.path.join(output_dir, f"stats_report{date_part}.txt")

    # --- Формируем сам отчёт ---
    report = f"""\
📊 Статистика рассылки
Период: {date_from.strftime('%Y-%m-%d') if date_from is not None else 'весь период'} — {date_to.strftime('%Y-%m-%d') if date_to is not None else 'до конца логов'}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📌 Всего отправленных сообщений: {sent_total}
✅ Успешно доставлено: {sent_success}
❌ Не доставлено: {sent_failed}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔴 Список ошибочных номеров (из исходных данных):
{error_table}
"""

    # --- Записываем отчёт в файл ---
    with open(report_file, "w", encoding="utf-8") as f:
        f.write(report)

    return report

# --- Пример использования ---
# Путь к отчёту:
# report_path = generate_delivery_stats_report(date_from="2025-07-20", date_to="2025-07-21")
# print(f"Отчёт сохранён: {report_path}")
