#!/usr/bin/env python3
# parser > lbma_parser > lbma_parser.py

import asyncio
import warnings
from pathlib import Path

import pandas as pd
import httpx

warnings.filterwarnings("ignore")


# Пути привязываем к папке lbma_parser/
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

XLSX_PATH = DATA_DIR / "lbma_kitco_subs.xlsx"


URLS = {
    "Gold": "https://prices.lbma.org.uk/json/gold_pm.json",
    "Silver": "https://prices.lbma.org.uk/json/silver.json",
    "Platinum": "https://prices.lbma.org.uk/json/platinum_pm.json",
    "Palladium": "https://prices.lbma.org.uk/json/palladium_pm.json",
}


def extract_first_value(value):
    """
    LBMA может возвращать значение как список.
    Например: [1234.5, "1234.5"]
    Берём первый элемент.
    """
    if isinstance(value, list):
        return value[0] if len(value) > 0 else None
    return value


async def get_raw_data(
    client: httpx.AsyncClient,
    url: str,
    metall: str,
) -> pd.DataFrame:
    """
    Асинхронно получает JSON по одному металлу.
    """
    response = await client.get(url, timeout=30)
    response.raise_for_status()

    raw_data = pd.read_json(response.text)

    if raw_data.empty:
        return pd.DataFrame(columns=["Date", metall])

    data = raw_data[["d", "v"]].copy()

    data["v"] = data["v"].apply(extract_first_value)
    data["d"] = pd.to_datetime(data["d"], errors="coerce")

    data[metall] = pd.to_numeric(data["v"], errors="coerce")

    data = data.rename(columns={"d": "Date"})
    data = data[["Date", metall]]
    data = data.dropna(subset=["Date"])

    # Как в оригинале: берём последние 10 записей
    return data.tail(10)


async def lbma_prescious_async():
    try:
        async with httpx.AsyncClient() as client:
            gold, silver, platinum, palladium = await asyncio.gather(
                get_raw_data(client, URLS["Gold"], "Gold"),
                get_raw_data(client, URLS["Silver"], "Silver"),
                get_raw_data(client, URLS["Platinum"], "Platinum"),
                get_raw_data(client, URLS["Palladium"], "Palladium"),
            )

        result_df = (
            gold.merge(silver, on="Date", how="outer")
            .merge(platinum, on="Date", how="outer")
            .merge(palladium, on="Date", how="outer")
        )

        result_df = result_df.sort_values("Date")
        result_df = result_df.reset_index(drop=True)

        # Читаем старую базу, если она есть
        if XLSX_PATH.exists():
            historical = pd.read_excel(XLSX_PATH)

            # Если Excel был сохранён с индексом, там может быть колонка
            # вида "Unnamed: 0" — удаляем её
            if historical.columns.size > 0 and str(
                historical.columns[0]
            ).startswith("Unnamed"):
                historical = historical.drop(columns=historical.columns[0])
        else:
            historical = pd.DataFrame(columns=result_df.columns)

        # Чтобы новые данные не перезатирали старые нулями,
        # не делаем fillna(0) до объединения.
        historical = historical.copy()
        result_df = result_df.copy()

        if "_priority" in historical.columns:
            historical = historical.drop(columns=["_priority"])

        if "_priority" in result_df.columns:
            result_df = result_df.drop(columns=["_priority"])

        historical["_priority"] = 0
        result_df["_priority"] = 1

        combined = pd.concat(
            [historical, result_df],
            ignore_index=True,
        )

        combined["Date"] = pd.to_datetime(
            combined["Date"],
            errors="coerce",
        )

        # Приводим все металлические колонки к numeric
        for col in combined.columns:
            if col not in ["Date", "_priority"]:
                combined[col] = pd.to_numeric(
                    combined[col],
                    errors="coerce",
                )

        combined = combined.dropna(subset=["Date"])

        # Сортируем так, чтобы новые строки были после старых
        combined = combined.sort_values(
            ["Date", "_priority"],
            kind="mergesort",
        )

        combined = combined.drop(columns=["_priority"])

        # groupby().last() оставит последнее НЕпустое значение
        result = combined.groupby("Date", as_index=False).last()

        # Если нужны нули вместо пропусков, как было в оригинале:
        result = result.fillna(0)

        result = result.sort_values("Date").reset_index(drop=True)

        with pd.ExcelWriter(
            XLSX_PATH,
            date_format="YYYY-MM-DD",
            datetime_format="YYYY-MM-DD",
        ) as writer:
            result.to_excel(
                writer,
                sheet_name="lbma_metall",
                index=False,
            )

        print("LBMA is done!!!")

    except Exception as error:
        print(f"Произошла ошибка LBMA: {error}")


__all__ = [
    "lbma_prescious_async",
]
