#!/usr/bin/env python3
# parser > cbr > cb_metall_parser.py

import asyncio
import warnings
from datetime import datetime
from pathlib import Path

import cfscrape
import pandas as pd

warnings.filterwarnings("ignore")


# Пути привязываем к папке cbr/
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

XLSX_PATH = DATA_DIR / "cb_metalls.xlsx"


def _fetch_sync(url: str):
    """
    Синхронный запрос через cfscrape.
    """
    scraper = cfscrape.create_scraper()

    response = scraper.get(
        url,
        timeout=30,
    )

    response.raise_for_status()

    return response


async def cb_metalls():
    try:
        current_year = datetime.now().year

        url = (
            "https://www.cbr.ru/hd_base/metall/metall_base_new/"
            "?UniDbQuery.Posted=True"
            f"&UniDbQuery.From=01.01.2023"
            f"&UniDbQuery.To=31.12.{current_year}"
            "&UniDbQuery.Gold=true"
            "&UniDbQuery.Silver=true"
            "&UniDbQuery.Platinum=true"
            "&UniDbQuery.Palladium=true"
            "&UniDbQuery.so=1"
        )

        response = await asyncio.to_thread(
            _fetch_sync,
            url,
        )

        metalls = pd.read_html(
            response.text.replace(",", ".")
        )[0]

        if metalls.shape[1] < 5:
            raise ValueError(
                "Таблица ЦБ по металлам содержит меньше 5 колонок"
            )

        metalls = metalls.rename(
            columns={
                metalls.columns[0]: "date",
                metalls.columns[1]: "gold",
                metalls.columns[2]: "silver",
                metalls.columns[3]: "platinum",
                metalls.columns[4]: "palladium",
            }
        )

        metalls["date"] = pd.to_datetime(
            metalls["date"],
            format="%d.%m.%Y",
            errors="coerce",
        )

        for col in ["gold", "silver", "platinum", "palladium"]:
            metalls[col] = pd.to_numeric(
                metalls[col]
                .astype(str)
                .str.replace(" ", "")
                .str.replace(",", "."),
                errors="coerce",
            )

        metalls = metalls.dropna(subset=["date"])
        metalls = metalls.sort_values("date").reset_index(drop=True)

        with pd.ExcelWriter(
            XLSX_PATH,
            date_format="YYYY-MM-DD",
            datetime_format="YYYY-MM-DD",
        ) as writer:
            metalls.to_excel(
                writer,
                sheet_name="cb_metalls",
                index=False,
            )

        print("CB_metalls parsing is DONE!")

    except Exception as error:
        print(f"Произошла ошибка CB_metalls: {error}")


__all__ = [
    "cb_metalls",
]
