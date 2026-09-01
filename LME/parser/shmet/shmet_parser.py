#!/usr/bin/env python3
# parser > shmet > shmet_parser.py

import asyncio
import warnings
from datetime import date
from pathlib import Path

import pandas as pd
import requests

warnings.filterwarnings("ignore")


# Пути привязываем к папке shmet/
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

XLSX_PATH = DATA_DIR / "shmet_historical.xlsx"

URL = "https://en.shmet.com/api/rest/enweb/spot/getSpotPrice"

PARAMS = {
    "code": "baseMetal",
    "size": 10,
    "currentLength": 0,
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}


def _fetch_day_data_sync() -> pd.DataFrame:
    """
    Синхронно запрашиваем SHMET API и готовим дневной срез по меди.
    """
    response = requests.get(
        URL,
        params=PARAMS,
        headers=HEADERS,
        timeout=30,
    )

    response.raise_for_status()

    payload = response.json()

    if "data" not in payload:
        raise ValueError("SHMET API вернул ответ без ключа 'data'")

    day_df = pd.DataFrame(payload["data"])

    if day_df.empty:
        return pd.DataFrame(
            columns=[
                "date",
                "price",
                "unit",
            ]
        )

    required_columns = {"name", "middle", "unit"}

    if not required_columns.issubset(day_df.columns):
        raise ValueError(
            "SHMET API вернул данные без ожидаемых колонок "
            "name / middle / unit"
        )

    day_df["date"] = date.today()

    copper_row = day_df[
        day_df["name"]
        .astype(str)
        .str.contains("cu", case=False, na=False)
    ]

    if copper_row.empty:
        raise ValueError("В ответе SHMET не найдена строка с медью / cu")

    result = copper_row[["date", "middle", "unit"]].copy()

    result = result.rename(
        columns={
            "middle": "price",
        }
    )

    result["date"] = pd.to_datetime(
        result["date"],
        errors="coerce",
    )

    result["price"] = (
        result["price"]
        .astype(str)
        .str.replace(",", "")
        .str.strip()
    )

    result["price"] = pd.to_numeric(
        result["price"],
        errors="coerce",
    )

    result = result.reset_index(drop=True)

    return result


async def shmet_optimized_async():
    try:
        day_update = await asyncio.to_thread(_fetch_day_data_sync)

        if day_update.empty:
            print("⚠️ SHMET: новые данные пустые. Файл не обновляется.")
            return

        # Читаем старую базу, если она есть
        if XLSX_PATH.exists():
            hist_data = pd.read_excel(XLSX_PATH)

            # Если файл был сохранён с индексом, может быть колонка
            # вида "Unnamed: 0"
            if hist_data.columns.size > 0 and str(
                hist_data.columns[0]
            ).startswith("Unnamed"):
                hist_data = hist_data.drop(
                    columns=hist_data.columns[0]
                )

            # Если date вдруг оказался в индексе
            if "date" not in hist_data.columns:
                hist_data = hist_data.reset_index()

                if (
                    "date" not in hist_data.columns
                    and "index" in hist_data.columns
                ):
                    hist_data = hist_data.drop(columns=["index"])
        else:
            hist_data = pd.DataFrame(columns=day_update.columns)

        new_df = pd.concat(
            [hist_data, day_update],
            ignore_index=True,
        )

        new_df["date"] = pd.to_datetime(
            new_df["date"],
            errors="coerce",
        )

        new_df["price"] = pd.to_numeric(
            new_df["price"],
            errors="coerce",
        )

        if "unit" in new_df.columns:
            new_df["unit"] = new_df["unit"].astype(str)

        new_df = new_df.dropna(subset=["date"])

        # Одна запись на дату — оставляем последнюю
        new_df = new_df.drop_duplicates(
            subset=["date"],
            keep="last",
        )

        new_df = new_df.sort_values("date").reset_index(drop=True)

        with pd.ExcelWriter(
            XLSX_PATH,
            date_format="YYYY-MM-DD",
            datetime_format="YYYY-MM-DD",
        ) as writer:
            new_df.to_excel(
                writer,
                sheet_name="SHMET",
                index=False,
            )

        print("SHMET is done!!!")

    except Exception as error:
        print(f"Произошла ошибка SHMET: {error}")


__all__ = [
    "shmet_optimized_async",
]
