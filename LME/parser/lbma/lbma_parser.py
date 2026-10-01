#!/usr/bin/env python3
# parser > lbma_parser > lbma_parser.py

import asyncio
import warnings
from pathlib import Path

import pandas as pd
from curl_cffi.requests import AsyncSession   # <-- заменили httpx

warnings.filterwarnings("ignore")


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


# Заголовки совместимы с профилем chrome124.
# impersonate сам подставит User-Agent, Accept, Sec-Ch-Ua и т.д.,
# поэтому здесь оставляем только то, что реально нужно.
HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.lbma.org.uk/prices-and-data",
    "Origin": "https://www.lbma.org.uk",
}


def extract_first_value(value):
    if isinstance(value, list):
        return value[0] if len(value) > 0 else None
    return value


async def get_raw_data(
    session: AsyncSession,
    url: str,
    metall: str,
) -> pd.DataFrame:
    # impersonate указываем прямо в запросе — это ключевое отличие
    response = await session.get(
        url,
        headers=HEADERS,
        impersonate="chrome124",
        timeout=30,
    )
    if response.status_code != 200:
        print(f"[LBMA] {metall}: HTTP {response.status_code}, "
              f"body[:200]={response.text[:200]!r}")
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
    return data.tail(10)


async def lbma_prescious_async():
    try:
        async with AsyncSession() as session:   # <-- больше не httpx
            gold, silver, platinum, palladium = await asyncio.gather(
                get_raw_data(session, URLS["Gold"], "Gold"),
                get_raw_data(session, URLS["Silver"], "Silver"),
                get_raw_data(session, URLS["Platinum"], "Platinum"),
                get_raw_data(session, URLS["Palladium"], "Palladium"),
            )

        result_df = (
            gold.merge(silver, on="Date", how="outer")
            .merge(platinum, on="Date", how="outer")
            .merge(palladium, on="Date", how="outer")
        )
        result_df = result_df.sort_values("Date").reset_index(drop=True)

        if XLSX_PATH.exists():
            historical = pd.read_excel(XLSX_PATH)
            if historical.columns.size > 0 and str(
                historical.columns[0]
            ).startswith("Unnamed"):
                historical = historical.drop(columns=historical.columns[0])
        else:
            historical = pd.DataFrame(columns=result_df.columns)

        historical = historical.copy()
        result_df = result_df.copy()

        if "_priority" in historical.columns:
            historical = historical.drop(columns=["_priority"])
        if "_priority" in result_df.columns:
            result_df = result_df.drop(columns=["_priority"])

        historical["_priority"] = 0
        result_df["_priority"] = 1

        combined = pd.concat([historical, result_df], ignore_index=True)
        combined["Date"] = pd.to_datetime(combined["Date"], errors="coerce")

        for col in combined.columns:
            if col not in ["Date", "_priority"]:
                combined[col] = pd.to_numeric(combined[col], errors="coerce")

        combined = combined.dropna(subset=["Date"])
        combined = combined.sort_values(
            ["Date", "_priority"], kind="mergesort")
        combined = combined.drop(columns=["_priority"])

        result = combined.groupby("Date", as_index=False).last()
        result = result.fillna(0)
        result = result.sort_values("Date").reset_index(drop=True)

        with pd.ExcelWriter(
            XLSX_PATH,
            date_format="YYYY-MM-DD",
            datetime_format="YYYY-MM-DD",
        ) as writer:
            result.to_excel(writer, sheet_name="lbma_metall", index=False)

        print("LBMA is done!!!")

    except Exception as error:
        print(f"Произошла ошибка LBMA: {error}")


__all__ = ["lbma_prescious_async"]
