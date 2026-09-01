#!/usr/bin/env python3
# parser > kitco > kitco.py

import asyncio
import warnings
from pathlib import Path

import pandas as pd
import httpx
from bs4 import BeautifulSoup

warnings.filterwarnings("ignore")

# Привязываем пути к папке kitco/
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

XLSX_PATH = DATA_DIR / "kitco_db.xlsx"
URL = "https://www.kitco.com/price/fixes/london-fix"

# HEADERS = {
#     "User-Agent": (
#         "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
#         "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
#     ),
#     "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
#     "Accept-Language": "en-US,en;q=0.5",
#     "Accept-Encoding": "gzip, deflate, br",
#     "Connection": "keep-alive",
#     "Upgrade-Insecure-Requests": "1",
# }

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}


def clean_cell(value) -> str:
    """
    Чистит ячейки/куски HTML от лишних тегов и комментариев.
    """
    return (
        str(value)
        .replace("<div>", "")
        .replace("</div>", "")
        .replace("<!-- -->", "")
        .strip()
    )


def get_part_number(value, part: int):
    """
    Например, значение может быть вида:
    2035.00/2036.00

    part=0 -> возьмёт левую часть
    part=1 -> возьмёт правую часть
    """
    try:
        parts = str(value).split("/")

        if len(parts) <= part:
            return None

        text = parts[part].strip().replace(",", "")
        return pd.to_numeric(text, errors="coerce")

    except Exception:
        return None


async def get_raw_data(
    client: httpx.AsyncClient,
    url: str,
) -> pd.DataFrame:
    """
    Асинхронно получает страницу Kitco и парсит таблицу London Fix.
    """
    response = await client.get(
        url,
        headers=HEADERS,
        timeout=30,
        follow_redirects=True,
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    day = soup.find_all("div", class_="grid")

    if not day:
        raise ValueError(
            "Не найдены блоки <div class='grid'> на странице Kitco"
        )

    day_content = [block.contents for block in day]

    # Чистим содержимое
    for container in day_content:
        for idx in range(len(container)):
            try:
                container[idx] = clean_cell(container[idx])
            except Exception:
                pass

    # Как в оригинале: убираем служебные строки
    day_content = day_content[1:]

    if len(day_content) > 1:
        day_content.pop(1)

    rows = []

    for element in day_content:
        if len(element) < 5:
            continue

        date = pd.to_datetime(element[0], errors="coerce")

        if pd.isna(date):
            continue

        rows.append(
            {
                "Date": date,
                "Gold": get_part_number(element[1], 1),
                "Silver": get_part_number(element[2], 0),
                "Platinum": get_part_number(element[3], 1),
                "Palladium": get_part_number(element[4], 1),
            }
        )

    day_update = pd.DataFrame(
        rows,
        columns=[
            "Date",
            "Gold",
            "Silver",
            "Platinum",
            "Palladium",
        ],
    )

    day_update = day_update.dropna(subset=["Date"])
    day_update = day_update.sort_values("Date").reset_index(drop=True)

    # Как в оригинале: берём последние 5 строк
    return day_update.tail(5)


async def kitco_parser_async():
    try:
        # 🔴 ГЛАВНОЕ ИСПРАВЛЕНИЕ: follow_redirects=True на уровне клиента
        async with httpx.AsyncClient(follow_redirects=True) as client:
            day_update = await get_raw_data(client, URL)

        if day_update.empty:
            print("⚠️ KITCO: новые данные пустые. Файл не обновляется.")
            return

        # Читаем старую базу, если она есть
        if XLSX_PATH.exists():
            historical_df = pd.read_excel(XLSX_PATH)

            # Если файл был сохранён с индексом, может быть колонка
            # вида "Unnamed: 0" — удаляем её
            if historical_df.columns.size > 0 and str(
                historical_df.columns[0]
            ).startswith("Unnamed"):
                historical_df = historical_df.drop(
                    columns=historical_df.columns[0]
                )

            # На случай, если Date вдруг оказался в индексе
            if "Date" not in historical_df.columns:
                historical_df = historical_df.reset_index()

                if (
                    "Date" not in historical_df.columns
                    and "index" in historical_df.columns
                ):
                    historical_df = historical_df.drop(columns=["index"])
        else:
            historical_df = pd.DataFrame(columns=day_update.columns)

        result = pd.concat(
            [historical_df, day_update],
            ignore_index=True,
        )

        result["Date"] = pd.to_datetime(
            result["Date"],
            errors="coerce",
        )

        # Приводим числовые колонки к нормальному типу
        for col in result.columns:
            if col != "Date":
                result[col] = pd.to_numeric(
                    result[col],
                    errors="coerce",
                )

        result = result.dropna(subset=["Date"])

        result = result.drop_duplicates(
            subset=["Date"],
            keep="last",
        )

        result = result.sort_values("Date").reset_index(drop=True)

        with pd.ExcelWriter(
            XLSX_PATH,
            date_format="YYYY-MM-DD",
            datetime_format="YYYY-MM-DD",
        ) as writer:
            result.to_excel(
                writer,
                sheet_name="kitco_metall",
                index=False,
            )

        print("KITCO_main is done!!!")

    except Exception as error:
        print(f"Произошла ошибка KITCO: {error}")


__all__ = [
    "kitco_parser_async",
]
