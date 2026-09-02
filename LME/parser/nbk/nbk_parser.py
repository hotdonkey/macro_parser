#!/usr/bin/env python3
# parser > nbk > nbk_parser.py

import asyncio
import warnings
from datetime import date
from pathlib import Path

import pandas as pd
import requests

warnings.filterwarnings("ignore")

# Привязываем пути к папке nbk/
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
XLSX_PATH = DATA_DIR / "nbk_tenge.xlsx"


async def nbk_tenge_async():
    try:
        year = date.today().year
        upper_bound = "01.01.2022"
        lower_bound = f"31.12.{year}"

        url = (
            "https://nationalbank.kz/ru/exchangerates/"
            "ezhednevnye-oficialnye-rynochnye-kursy-valyut/report"
            f"?rates%5B%5D=5&beginDate={upper_bound}&endDate={lower_bound}"
        )

        # Запрос с повторными попытками
        page = None
        for attempt in range(7):
            try:
                response = requests.get(url, timeout=30)
                response.raise_for_status()
                page = response
                break
            except Exception as e:
                print(f"⚠️ NBK попытка {attempt + 1}/7 не удалась: {e}")
                await asyncio.sleep(2)

        if page is None:
            print("❌ NBK: не удалось получить данные после 7 попыток")
            return

        # Парсинг таблицы
        tables = pd.read_html(page.text)
        if not tables:
            print("❌ NBK: таблица не найдена на странице")
            return

        df = tables[0]

        # Первая колонка — это дата
        date_col = df.columns[0]
        df = df.rename(columns={date_col: "date"})
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df = df.dropna(subset=["date"])

        # Приводим числовые колонки к numeric
        for col in df.columns:
            if col != "date":
                df[col] = pd.to_numeric(df[col], errors="coerce")

        df = df.sort_values("date").reset_index(drop=True)

        # 🔴 ЧИТАЕМ СТАРЫЙ ФАЙЛ И ОБЪЕДИНЯЕМ
        if XLSX_PATH.exists():
            try:
                historical = pd.read_excel(XLSX_PATH)
                # Убираем служебную колонку индекса, если есть
                if historical.columns.size > 0 and str(
                    historical.columns[0]
                ).startswith("Unnamed"):
                    historical = historical.drop(columns=historical.columns[0])

                # Объединяем старое и новое
                combined = pd.concat([historical, df], ignore_index=True)
            except Exception as e:
                print(f"⚠️ NBK: ошибка чтения старого файла: {e}")
                combined = df
        else:
            combined = df

        # Удаляем дубликаты по дате, оставляем последнюю запись
        combined = combined.sort_values("date").drop_duplicates(
            subset=["date"], keep="last"
        )
        combined = combined.reset_index(drop=True)

        # Сохраняем
        with pd.ExcelWriter(
            XLSX_PATH,
            date_format="YYYY-MM-DD",
            datetime_format="YYYY-MM-DD",
        ) as writer:
            combined.to_excel(writer, sheet_name="tenge", index=False)

        print(f"NBK_tenge parsing is DONE! ({len(combined)} строк)")

    except Exception as error:
        print(f"❌ Ошибка NBK: {error}")


__all__ = ["nbk_tenge_async"]
