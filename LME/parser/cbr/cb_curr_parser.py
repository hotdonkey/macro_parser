#!/usr/bin/env python3
# parser > cbr > cb_curr_parser.py

import asyncio
import warnings
from datetime import datetime
from io import StringIO
from pathlib import Path

import cfscrape
import pandas as pd

warnings.filterwarnings("ignore")


# Пути привязываем к папке cbr/
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

XLSX_PATH = DATA_DIR / "cb_currency.xlsx"


CURRENCY_CODES = {
    "USD": "R01235",
    "EUR": "R01239",
    "Australian_Dollar": "R01010",
    "China_Yuan": "R01375",
    "British_Pound": "R01035",
    "Kazakhstan_Tenge": "R01335",
    "Japanese_Yen": "R01820",
    "Swiss_Franc": "R01775",
}


def _fetch_sync(url: str):
    """
    Синхронный запрос через cfscrape.
    Выносится отдельно, чтобы запускать через asyncio.to_thread().
    """
    scraper = cfscrape.create_scraper()

    response = scraper.get(
        url,
        timeout=30,
    )

    response.raise_for_status()

    return response


async def get_currency(currency: str):
    """
    Асинхронная обёртка над синхронным cfscrape-запросом.
    """
    if currency not in CURRENCY_CODES:
        raise ValueError(f"Неизвестная валюта: {currency}")

    current_date = datetime.today().strftime("%d.%m.%Y")

    url = (
        "https://www.cbr.ru/currency_base/dynamics/?UniDbQuery.Posted=True"
        "&UniDbQuery.so=1&UniDbQuery.mode=1"
        "&UniDbQuery.date_req1=&UniDbQuery.date_req2="
        f"&UniDbQuery.VAL_NM_RQ={CURRENCY_CODES[currency]}"
        f"&UniDbQuery.From=01.01.2023&UniDbQuery.To={current_date}"
    )

    return await asyncio.to_thread(
        _fetch_sync,
        url,
    )


def data_reconstruction(scraped_data, name: str) -> pd.DataFrame:
    """
    Преобразует HTML-таблицу ЦБ в DataFrame.
    """
    try:
        data = pd.read_html(
            scraped_data.text.replace(",", ".")
        )[0]
    except Exception as error:
        raise ValueError(
            f"Не удалось прочитать таблицу для {name}: {error}"
        )

    if data.shape[0] < 3 or data.shape[1] < 3:
        return pd.DataFrame(
            columns=[
                "date",
                "unit",
                "nominal",
            ]
        )

    data.columns = data.iloc[1]
    data = data.iloc[2:]

    data = data.rename(
        columns={
            data.columns[0]: "date",
            data.columns[1]: "unit",
            data.columns[2]: "nominal",
        }
    ).reset_index(drop=True)

    # Оставляем поведение, близкое к оригиналу
    data = pd.read_csv(
        StringIO(data.to_string(index=False)),
        sep=r"\s+",
    )

    data["date"] = pd.to_datetime(
        data["date"],
        format="%d.%m.%Y",
        errors="coerce",
    )

    for col in ["unit", "nominal"]:
        if col in data.columns:
            data[col] = pd.to_numeric(
                data[col],
                errors="coerce",
            )

    data = data.dropna(subset=["date"])
    data = data.sort_values("date").reset_index(drop=True)

    print(f"{name} is done!")

    return data


async def cb_currency():
    try:
        currencies = tuple(CURRENCY_CODES.keys())

        raw_responses = await asyncio.gather(
            *[
                get_currency(currency)
                for currency in currencies
            ]
        )

        frames = [
            data_reconstruction(raw, name)
            for raw, name in zip(raw_responses, currencies)
        ]

        with pd.ExcelWriter(
            XLSX_PATH,
            date_format="YYYY-MM-DD",
            datetime_format="YYYY-MM-DD",
        ) as writer:
            for name, frame in zip(currencies, frames):
                frame.to_excel(
                    writer,
                    sheet_name=name,
                    index=False,
                )

        print("CB_currency parsing is DONE!")

    except Exception as error:
        print(f"Произошла ошибка CB_currency: {error}")


__all__ = [
    "cb_currency",
]
