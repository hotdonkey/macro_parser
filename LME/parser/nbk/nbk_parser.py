#!/usr/bin/env python3
# parser > nbk > nbk_parser.py

import asyncio
import warnings
from datetime import date
from pathlib import Path

import pandas as pd
import requests

warnings.filterwarnings("ignore")


# Пути привязываем к папке nbk/
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

XLSX_PATH = DATA_DIR / "nbk_tenge.xlsx"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}


def _fetch_and_parse_sync() -> pd.DataFrame:
    """
    Синхронный запрос и парсинг таблицы Национального банка Казахстана.
    Выносится отдельно, чтобы запускать через asyncio.to_thread().
    """
    year = date.today().year

    upper_bound = "01.01.2022"
    lower_bound = f"31.12.{year}"

    url = (
        "https://nationalbank.kz/ru/exchangerates/"
        "ezhednevnye-oficialnye-rynochnye-kursy-valyut/report"
    )

    params = {
        "rates[]": "5",
        "beginDate": upper_bound,
        "endDate": lower_bound,
    }

    last_error = None

    # Делаем несколько попыток, так как источник действительно нестабильный
    for attempt in range(7):
        try:
            response = requests.get(
                url,
                params=params,
                headers=HEADERS,
                timeout=30,
            )

            response.raise_for_status()

            tables = pd.read_html(response.text)

            if not tables:
                raise ValueError("NBK вернул страницу без таблиц")

            df = tables[0].copy()

            if df.empty:
                return pd.DataFrame(columns=["date"])

            # Переименовываем первую колонку в date,
            # даже если она называлась "Unnamed: 0" или как-то иначе
            first_col = df.columns[0]

            df = df.rename(
                columns={
                    first_col: "date",
                }
            )

            df["date"] = pd.to_datetime(
                df["date"],
                errors="coerce",
                dayfirst=True,
            )

            df = df.dropna(subset=["date"])
            df = df.sort_values("date").reset_index(drop=True)

            return df

        except Exception as error:
            last_error = error

    raise RuntimeError(
        f"NBK не ответил корректно после нескольких попыток: {last_error}"
    )


async def nbk_tenge_async():
    try:
        df = await asyncio.to_thread(_fetch_and_parse_sync)

        if df.empty:
            print("⚠️ NBK: таблица пустая. Файл не обновляется.")
            return

        with pd.ExcelWriter(
            XLSX_PATH,
            date_format="YYYY-MM-DD",
            datetime_format="YYYY-MM-DD",
        ) as writer:
            df.to_excel(
                writer,
                sheet_name="tenge",
                index=False,
            )

        print("NBK_tenge parsing is DONE!")

        return df

    except Exception as error:
        print(f"Произошла ошибка NBK: {error}")


__all__ = [
    "nbk_tenge_async",
]
