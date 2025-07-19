#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Модифицированная версия main.py для работы со статусами конкретной воронки 4524700
"""

import os
import json
import re
import requests
from itertools import islice
import phonenumbers
from pathlib import Path

class AmoCRMCategoryManager:
    """
    Класс-обёртка над REST-API Kommo (amoCRM).
    • Определяет рабочий домен (`.amocrm.ru` или `.kommo.com`)
    • Отдаёт воронки, этапы и сделки в виде списков/словарей
    • Опционально одним запросом подтягивает контакты, чтобы показать телефоны
    """

    def __init__(self) -> None:
        """Читает `conf.json` и определяет базовый URL для API."""
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
        """Возвращает первый API-домен, который отвечает 200 на `/account`."""
        for url in self._base_urls:
            try:
                if requests.get(f"{url}/account", headers=self.headers, timeout=6
                ).status_code == 200:
                    return url
            except requests.exceptions.RequestException:
                pass
        raise RuntimeError("Не удалось найти рабочий домен Kommo")

    def get_pipelines(self) -> list[tuple[int, str]]:
        """Список воронок: [(id, name), …]."""
        r = requests.get(f"{self.base_url}/leads/pipelines",
                        headers=self.headers, timeout=20)
        r.raise_for_status()
        return [(p["id"], p["name"])
                for p in r.json()["_embedded"]["pipelines"]]

    def get_pipeline_statuses(self, pipeline_id: int) -> list[tuple[int, str]]:
        """Этапы указанной воронки: [(id, name), …]."""
        r = requests.get(f"{self.base_url}/leads/pipelines/{pipeline_id}",
                        headers=self.headers, timeout=20)
        r.raise_for_status()
        return [(s["id"], s["name"])
                for s in r.json()["_embedded"]["statuses"]]

    def get_leads(self, pipeline_id: int, status_id: int) -> list[dict]:
        """
        Все сделки этапа; у каждой сделки уже есть вложенный список id контактов.
        """
        out, page = [], 1
        while True:
            params = {
                "limit": 250,
                "page": page,
                "filter[statuses][0][pipeline_id]": pipeline_id,
                "filter[statuses][0][status_id]": status_id,
                "with": "contacts",
            }
            r = requests.get(f"{self.base_url}/leads",
                           headers=self.headers,
                           params=params, timeout=20)
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
        """
        Возвращает ВСЕ сделки во всех статусах указанной воронки.
        """
        leads_all: list[dict] = []
        # перебираем статусы и собираем сделки
        for status_id, _ in self.get_pipeline_statuses(pipeline_id):
            leads_all.extend(self.get_leads(pipeline_id, status_id))
        return leads_all

    def get_contacts_bulk(self, ids: list[int]) -> dict[int, dict]:
        """
        Возвращает словарь контактов {id: объект}. Запрашивает пачками по 200 id.
        """
        result: dict[int, dict] = {}
        ids_iter = iter(ids)
        while chunk := list(islice(ids_iter, 200)):
            params = {"with": "custom_fields_values"}
            params.update({f"id[{i}]": cid for i, cid in enumerate(chunk)})
            r = requests.get(f"{self.base_url}/contacts",
                           headers=self.headers,
                           params=params, timeout=20)
            if r.status_code != 200:
                continue
            for c in r.json()["_embedded"]["contacts"]:
                result[c["id"]] = c
        return result

    @staticmethod
    def extract_phone(cfv: list[dict]) -> str:
        """Возвращает первый телефон из custom_fields_values контакта."""
        for fld in cfv or []:
            if fld.get("field_code") == "PHONE":
                for val in fld.get("values", []):
                    phone = str(val.get("value", "")).strip()
                    if phone:
                        return phone
        return ""

    def normalize_phone(self, phone: str):
        """
        Приводит телефон к E.164 (+79991234567) или возвращает False.
        Поддерживает:
        • «8XXXXXXXXXX» → «+7XXXXXXXXXX»
        • «7XXXXXXXXXX» → «+7XXXXXXXXXX»
        • «9XXXXXXXXX» → «+79XXXXXXXXX» (коротко без кода страны)
        • убирает пробелы, скобки, дефисы
        """
        # 1. оставить только цифры
        digits = re.sub(r"\D", "", phone)
        
        # 2. Россия: варианты без «+7»
        if digits.startswith("8") and len(digits) == 11:
            digits = "7" + digits[1:]
        elif digits.startswith("7") and len(digits) == 11:
            pass  # уже в виде 7XXXXXXXXXX
        elif digits.startswith("9") and len(digits) == 10:
            digits = "7" + digits  # добавили пропущенную «7»
        
        # 3. сформировать международный вид
        digits = "+" + digits
        
        # 4. проверить через phonenumbers
        try:
            parsed = phonenumbers.parse(digits, None)
            if phonenumbers.is_valid_number(parsed):
                return phonenumbers.format_number(
                    parsed, phonenumbers.PhoneNumberFormat.E164
                )
        except phonenumbers.phonenumberutil.NumberParseException:
            pass
        return False

# ЦЕЛЕВАЯ ВОРОНКА - здесь указываем ID воронки, статусы которой нужно показывать
TARGET_PIPELINE_ID = 4524700

def build_funnels_snapshot() -> dict:
    """
    МОДИФИЦИРОВАННАЯ ФУНКЦИЯ: Показывает статусы конкретной воронки как отдельные 'воронки'
    """
    mgr = AmoCRMCategoryManager()
    snapshot = {"funnels": []}
    
    try:
        # Получаем статусы целевой воронки вместо всех воронок
        statuses = mgr.get_pipeline_statuses(TARGET_PIPELINE_ID)
        
        for status_id, status_name in statuses:
            # Каждый статус становится отдельной 'воронкой' в боте
            fname = f"status_{status_id}_{status_name.replace(' ', '_').replace('/', '_')}.json"
            snapshot["funnels"].append({
                "name": status_name, 
                "file": fname,
                "pipeline_id": TARGET_PIPELINE_ID,
                "status_id": status_id
            })
        
        # Создаем папку если её нет
        os.makedirs("amocrm_contacts", exist_ok=True)
        
        # Сохраняем снимок
        (Path(__file__).parent / "amocrm_contacts" / "funnels.json").write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        
    except Exception as e:
        print(f"Ошибка при получении статусов воронки {TARGET_PIPELINE_ID}: {e}")
        
    return snapshot

def console_test() -> None:
    """CLI: выводит данные в консоль, читает ввод пользователя."""
    mgr = AmoCRMCategoryManager()
    
    while True:
        print("\nМЕНЮ\n"
              "1) Показать все воронки\n"
              f"2) Показать статусы целевой воронки ({TARGET_PIPELINE_ID})\n"
              "3) Показать сделки статуса\n"
              "4) Тест новой функции build_funnels_snapshot\n"
              "5) Выход")
        
        choice = input("→ ").strip()
        
        if choice == "1":
            for pid, name in mgr.get_pipelines():
                print(f"{pid}: {name}")
                
        elif choice == "2":
            for sid, name in mgr.get_pipeline_statuses(TARGET_PIPELINE_ID):
                print(f"{sid}: {name}")
                
        elif choice == "3":
            sid = input("ID статуса: ").strip()
            if not sid.isdigit():
                print("❗ ID должно быть числом")
                continue
                
            leads = mgr.get_leads(TARGET_PIPELINE_ID, int(sid))
            if not leads:
                print("Сделки не найдены")
                continue
                
            # bulk-загрузка контактов
            cids = [c["id"] for l in leads for c in l["_embedded"]["contacts"]]
            contacts = mgr.get_contacts_bulk(cids)
            
            for lead in leads:
                phone, contact_name = "", ""
                for c in lead["_embedded"]["contacts"]:
                    co = contacts.get(c["id"], {})
                    cfv = co.get("custom_fields_values", [])
                    phone = mgr.extract_phone(cfv)
                    if phone:
                        contact_name = co.get("name", "")
                        break
                
                normalized = mgr.normalize_phone(phone)
                if normalized is False:
                    print(f"{lead['id']}: {lead['name']} — False ({phone}) — {contact_name}")
                else:
                    print(f"{lead['id']}: {lead['name']} — {normalized} — {contact_name}")
            
            print(f"Всего сделок: {len(leads)}")
            
        elif choice == "4":
            print("Тестируем новую функцию...")
            snapshot = build_funnels_snapshot()
            print("Результат:")
            print(json.dumps(snapshot, ensure_ascii=False, indent=2))
            
        elif choice == "5":
            break
        else:
            print("❗ Нет такого пункта")

if __name__ == "__main__":
    console_test()
