#!/usr/bin/env python3
# parser > lbma_parser > lbma_parser.py

import asyncio
import json
import warnings
from pathlib import Path

import pandas as pd
from scrapling.fetchers import StealthySession

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


# ===== НАСТРОЙКА ПРОКСИ =====
# Если IP заблокирован Cloudflare (как у тебя: 94.137.237.243) —
# без прокси скрипт, скорее всего, снова получит 403.
# Формат: "http://user:pass@host:port" или "socks5://host:port"
# PROXY = None  # замени на строку с прокси, если он есть
PROXY = "http://K84kcE:Ss1Lk1@196.18.164.235:8000"


def extract_first_value(value):
    """
    LBMA может возвращать значение как список.
    Например: [1234.5, "1234.5"]
    Берём первый элемент.
    """
    if isinstance(value, list):
        return value[0] if len(value) > 0 else None
    return value


# ================================================================
# Синхронный блок работы со Scrapling.
# Запускается в отдельном потоке через asyncio.to_thread(),
# чтобы не блокировать event loop в asyncio.gather().
# ================================================================
def _lbma_sync_worker() -> dict[str, pd.DataFrame]:
    """
    Открывает одну StealthySession и последовательно тянет 4 металла.
    Возвращает словарь {metall: DataFrame}.
    """
    results: dict[str, pd.DataFrame] = {}

    with StealthySession(
        headless=True,           # для серверов; для отладки — False
        solve_cloudflare=True,   # ключевой параметр обхода челленджа
        network_idle=True,       # ждём, пока сеть успокоится
        block_webrtc=True,       # блокируем WebRTC (утечка IP)
        hide_canvas=True,        # защита от canvas-фингерпринтинга
        proxy=PROXY,
    ) as session:
        print("[LBMA] Scrapling session opened")

        for metal, url in URLS.items():
            print(f"[LBMA] fetching {metal}...")
            results[metal] = _fetch_one(session, url, metal)

    return results


def _fetch_one(session: StealthySession, url: str, metall: str) -> pd.DataFrame:
    """
    Один запрос внутри сессии. Cloudflare уже пройден на первом,
    cookie cf_clearance переиспользуется для последующих.
    """
    try:
        page = session.fetch(
            url,
            solve_cloudflare=True,
            network_idle=True,
            timeout=60000,
        )
    except Exception as e:
        print(f"[LBMA] {metall}: fetch error: {e}")
        return pd.DataFrame(columns=["Date", metall])

    if page.status != 200:
        print(f"[LBMA] {metall}: HTTP {page.status}. "
              f"Похоже, нужен прокси / другой IP.")
        return pd.DataFrame(columns=["Date", metall])

    try:
        raw_json = json.loads(page.body)
    except json.JSONDecodeError as e:
        print(f"[LBMA] {metall}: JSON decode error: {e}")
        print(f"[LBMA] body[:200]: {page.body[:200]!r}")
        return pd.DataFrame(columns=["Date", metall])

    raw_data = pd.DataFrame(raw_json)
    if raw_data.empty or "d" not in raw_data.columns or "v" not in raw_data.columns:
        return pd.DataFrame(columns=["Date", metall])

    data = raw_data[["d", "v"]].copy()
    data["v"] = data["v"].apply(extract_first_value)
    data["d"] = pd.to_datetime(data["d"], errors="coerce")
    data[metall] = pd.to_numeric(data["v"], errors="coerce")

    data = data.rename(columns={"d": "Date"})
    data = data[["Date", metall]]
    data = data.dropna(subset=["Date"])
    return data.tail(10)


# ================================================================
# Публичный интерфейс — совместим с main.py:
#   from lbma import lbma_prescious_async
#   tasks = {"lbma": lbma_prescious_async(), ...}
# ================================================================
async def lbma_prescious_async():
    try:
        # Синхронный Scrapling → в отдельный поток.
        # asyncio.gather продолжит работать параллельно
        # с остальными парсерами, пока браузер решает Cloudflare.
        results = await asyncio.to_thread(_lbma_sync_worker)

        gold = results.get("Gold", pd.DataFrame(columns=["Date", "Gold"]))
        silver = results.get("Silver", pd.DataFrame(
            columns=["Date", "Silver"]))
        platinum = results.get("Platinum", pd.DataFrame(
            columns=["Date", "Platinum"]))
        palladium = results.get("Palladium", pd.DataFrame(
            columns=["Date", "Palladium"]))

        # Если все четыре пустые — сохранять нечего
        if all(df.empty for df in (gold, silver, platinum, palladium)):
            print("[LBMA] all responses empty — skip save")
            return

        # ===== Объединение (логика без изменений) =====
        result_df = (
            gold.merge(silver, on="Date", how="outer")
            .merge(platinum, on="Date", how="outer")
            .merge(palladium, on="Date", how="outer")
        )
        result_df = result_df.sort_values("Date").reset_index(drop=True)

        # ===== Читаем старую базу, если она есть =====
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
            ["Date", "_priority"],
            kind="mergesort",
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

        print("[LBMA] is done!!!")

    except Exception as error:
        # Не роняем gather — main.py ловит через return_exceptions=True
        print(f"[LBMA] Произошла ошибка: {error}")
        raise


__all__ = [
    "lbma_prescious_async",
]
