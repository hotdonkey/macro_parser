#!/usr/bin/env python3
# parser > westmetall > westmetall.py

import asyncio
import warnings
from pathlib import Path

import pandas as pd
import requests

warnings.filterwarnings("ignore")


# Пути привязываем к папке westmetall/
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

XLSX_PATH = DATA_DIR / "LME_westmetall_db.xlsx"


def get_data(metall: str, col_name: str) -> pd.DataFrame:
    """
    Скачивает таблицу по одному металлу.
    Это синхронная функция, но вызываться она будет через asyncio.to_thread().
    """
    url = (
        "https://www.westmetall.com/en/markdaten.php"
        f"?action=table&field=LME_{metall}_cash"
    )

    response = requests.get(url, timeout=30)
    response.raise_for_status()

    # Берём первую таблицу и первые 30 строк
    df = pd.read_html(response.text)[0].iloc[:30, :2].copy()

    # Принудительно задаём нормальные имена колонок
    df.columns = ["date", col_name]

    # Убираем возможную строку-заголовок внутри данных
    df = df[df["date"].astype(str).str.lower() != "date"]

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df[col_name] = pd.to_numeric(df[col_name], errors="coerce")

    df = df.dropna().reset_index(drop=True)

    return df


async def westmetall_async():
    try:
        metals = (
            ("Al", "aluminium"),
            ("Cu", "copper"),
            ("Pb", "lead"),
            ("Ni", "nickel"),
            ("Zn", "zink"),
            ("Sn", "tin"),
        )

        # Запросы выполняем в отдельных потоках, чтобы не блокировать event loop
        tasks = [
            asyncio.to_thread(get_data, metal, col_name)
            for metal, col_name in metals
        ]

        frames = await asyncio.gather(*tasks)

        result = frames[0]

        for frame in frames[1:]:
            result = result.merge(frame, on="date", how="left")

        # Если старый файл есть — читаем его.
        # Если файла ещё нет — создаём пустой DataFrame с нужными колонками.
        if XLSX_PATH.exists():
            old_data = pd.read_excel(XLSX_PATH)

            # Если там есть служебный индексный столбец вроде "Unnamed: 0"
            if old_data.columns.size > 0 and str(
                old_data.columns[0]
            ).startswith("Unnamed"):
                old_data = old_data.drop(columns=old_data.columns[0])
        else:
            old_data = pd.DataFrame(columns=result.columns)

        final_data = pd.concat(
            [old_data, result],
            ignore_index=True,
        )

        final_data["date"] = pd.to_datetime(
            final_data["date"],
            errors="coerce",
        )

        # Приводим числовые колонки к numeric
        for col in final_data.columns:
            if col != "date":
                final_data[col] = pd.to_numeric(
                    final_data[col],
                    errors="coerce",
                )

        final_data = final_data.dropna(subset=["date"])

        final_data = final_data.drop_duplicates(
            subset="date",
            keep="last",
        )

        final_data = final_data.sort_values("date").reset_index(drop=True)

        with pd.ExcelWriter(
            XLSX_PATH,
            date_format="YYYY-MM-DD",
            datetime_format="YYYY-MM-DD",
        ) as writer:
            final_data.to_excel(
                writer,
                sheet_name="LME_westmetall",
                index=True,
            )

        print("WESTMETALL is done!!!")

    except Exception as error:
        print(f"❌ Ошибка westmetall: {error}")


__all__ = [
    "westmetall_async",
]
