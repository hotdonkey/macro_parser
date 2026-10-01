#!/usr/bin/env python3
# parser > lbma_parser > lbma_parser.py

import asyncio
import warnings
from pathlib import Path

import pandas as pd
from fredapi import Fred

warnings.filterwarnings("ignore")


# Пути привязываем к папке lbma_parser/
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

XLSX_PATH = DATA_DIR / "lbma_kitco_subs.xlsx"


# ===== НАСТРОЙКА FRED =====
# !!! ВАЖНО: Замените на ваш личный API-ключ, полученный на сайте FRED !!!
FRED_API_KEY = "506aa5b612d240c1fc5b959e8d77553b"

# Соответствие: металл -> код серии в FRED
# Для золота и серебра есть официальные серии LBMA (PM фиксинг).
# Для платины и палладия точных аналогов на FRED нет,
# поэтому используются данные с Лондонской биржи металлов (LME).
FRED_SERIES = {
    "Gold":      "GOLDPMGBD228NLBM",  # LBMA Gold Price: PM Fixing, USD
    "Silver":    "SILVERPMGBD228NLBM",  # LBMA Silver Price: PM Fixing, USD
    # Внимание: для платины и палладия используются данные LME, а не LBMA.
    # Это может быть приемлемой заменой, но стоит знать об этом.
    "Platinum":  "PLATINUMLME",        # LME Platinum Price, USD
    "Palladium": "PALLADIUMLME",       # LME Palladium Price, USD
}


def fetch_metal_from_fred(fred_client: Fred, metal: str, series_id: str) -> pd.DataFrame:
    """
    Забирает данные одного металла из FRED по коду серии.
    Возвращает DataFrame с колонками ['Date', metal].
    """
    try:
        # Получаем данные с помощью библиотеки fredapi
        series = fred_client.get_series(series_id)
    except Exception as e:
        print(f"[LBMA/FRED] {metal}: ошибка загрузки серии {series_id}: {e}")
        return pd.DataFrame(columns=["Date", metal])

    if series is None or series.empty:
        print(f"[LBMA/FRED] {metal}: пустой ответ для серии {series_id}")
        return pd.DataFrame(columns=["Date", metal])

    # Преобразуем в DataFrame
    data = series.reset_index()
    data.columns = ["Date", metal]
    data["Date"] = pd.to_datetime(data["Date"], errors="coerce")
    data[metal] = pd.to_numeric(data[metal], errors="coerce")
    data = data.dropna(subset=["Date"])

    # Как в оригинале: последние 10 записей
    return data.tail(10)


async def lbma_prescious_async():
    """
    Публичный интерфейс, совместимый с main.py.
    Данные берутся из FRED (без Cloudflare, без прокси).
    """
    try:
        # Инициализируем клиент FRED
        fred_client = Fred(api_key=FRED_API_KEY)

        # Синхронный сбор данных → в отдельный поток,
        # чтобы не блокировать event loop в asyncio.gather()
        results = await asyncio.to_thread(_fetch_all_metals_fred, fred_client)

        gold = results.get("Gold", pd.DataFrame(columns=["Date", "Gold"]))
        silver = results.get("Silver", pd.DataFrame(
            columns=["Date", "Silver"]))
        platinum = results.get("Platinum", pd.DataFrame(
            columns=["Date", "Platinum"]))
        palladium = results.get("Palladium", pd.DataFrame(
            columns=["Date", "Palladium"]))

        if all(df.empty for df in (gold, silver, platinum, palladium)):
            print("[LBMA/FRED] все ответы пустые — сохранение пропущено")
            return

        # ===== Объединение =====
        result_df = (
            gold.merge(silver, on="Date", how="outer")
            .merge(platinum, on="Date", how="outer")
            .merge(palladium, on="Date", how="outer")
        )
        result_df = result_df.sort_values("Date").reset_index(drop=True)

        # ===== Чтение старой базы =====
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
            ["Date", "_priority"], kind="mergesort"
        )
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

        print("[LBMA/FRED] is done!!!")

    except Exception as error:
        print(f"[LBMA/FRED] Произошла ошибка: {error}")
        raise


def _fetch_all_metals_fred(fred_client: Fred) -> dict[str, pd.DataFrame]:
    """Синхронный сбор всех четырёх металлов из FRED."""
    results: dict[str, pd.DataFrame] = {}
    for metal, series_id in FRED_SERIES.items():
        print(f"[LBMA/FRED] Загрузка {metal} ({series_id})...")
        results[metal] = fetch_metal_from_fred(fred_client, metal, series_id)
    return results


__all__ = [
    "lbma_prescious_async",
]
