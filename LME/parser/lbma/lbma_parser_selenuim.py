#!/usr/bin/env python3
# parser > lbma_parser > lbma_parser.py

import asyncio
import json
import time
import warnings
from pathlib import Path

import pandas as pd

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select

import undetected_chromedriver as uc

warnings.filterwarnings("ignore")


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

XLSX_PATH = DATA_DIR / "lbma_kitco_subs.xlsx"


# ===== НАСТРОЙКА =====
PAGE_URL = "https://www.lbma.org.uk/prices-and-data/lbma-precious-metal-prices"

METALS = {
    "gold":      "Gold",
    "silver":    "Silver",
    "platinum":  "Platinum",
    "palladium": "Palladium",
}

# Резидентный прокси, если твой IP забанен на prices.lbma.org.uk
# Формат: "http://user:pass@host:port" или "socks5://host:port"
PROXY = None

CF_WAIT = 10   # ожидание решения Cloudflare после открытия страницы
AJAX_WAIT = 3  # ожидание ajax-запроса после клика


# ================================================================
# Создание драйвера с поддержкой network-логов (CDP)
# ================================================================
def _build_driver():
    options = uc.ChromeOptions()
    # options.add_argument("--headless=new")  # для отладки лучше с GUI
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1440,900")
    options.add_argument("--disable-blink-features=AutomationControlled")

    # Включаем сбор performance-логов (это включает Network domain в CDP)
    options.set_capability("goog:loggingPrefs", {"performance": "ALL"})

    if PROXY:
        options.add_argument(f"--proxy-server={PROXY}")

    driver = uc.Chrome(options=options, use_subprocess=True)
    return driver


# ================================================================
# Парсинг сетевых логов CDP
# ================================================================
def _collect_responses(driver) -> dict[str, str]:
    """
    Забирает все performance-логи, находит Network.responseReceived
    и возвращает {requestId: url} для ответов от prices.lbma.org.uk.
    """
    responses = {}
    try:
        logs = driver.get_log("performance")
    except Exception as e:
        print(f"[LBMA/Selenium] get_log error: {e}")
        return responses

    for entry in logs:
        try:
            msg = json.loads(entry["message"])["message"]
        except (json.JSONDecodeError, KeyError):
            continue

        if msg.get("method") != "Network.responseReceived":
            continue

        params = msg.get("params", {})
        response = params.get("response", {})
        url = response.get("url", "")
        request_id = params.get("requestId")

        if "prices.lbma.org.uk" in url and request_id:
            responses[request_id] = url

    return responses


def _get_response_body(driver, request_id: str) -> str | None:
    """Через CDP забирает тело ответа по requestId."""
    try:
        body = driver.execute_cdp_cmd(
            "Network.getResponseBody", {"requestId": request_id}
        )
        return body.get("body")
    except Exception as e:
        # Тело может быть уже выгружено из памяти — это нормально,
        # просто пропускаем и ищем следующий requestId
        print(f"[LBMA/Selenium] getResponseBody error for {request_id}: {e}")
        return None


# ================================================================
# Основная логика
# ================================================================
def _scrape_via_browser() -> dict[str, pd.DataFrame]:
    results: dict[str, pd.DataFrame] = {}
    driver = _build_driver()

    try:
        print("[LBMA/Selenium] Открываем страницу LBMA...")
        driver.get(PAGE_URL)
        time.sleep(CF_WAIT)

        # Сбрасываем накопленные логи от загрузки страницы
        try:
            driver.get_log("performance")
        except Exception:
            pass

        for option_value, metal_name in METALS.items():
            print(f"[LBMA/Selenium] Обрабатываем {metal_name}...")

            try:
                _select_metal(driver, option_value)
                _click_pm(driver)
                time.sleep(AJAX_WAIT)

                df = _extract_metal_json(driver, metal_name)
                results[metal_name] = df
                print(
                    f"[LBMA/Selenium] {metal_name}: получено {len(df)} строк")

            except Exception as e:
                print(f"[LBMA/Selenium] {metal_name}: ошибка: {e}")
                results[metal_name] = pd.DataFrame(
                    columns=["Date", metal_name])

    finally:
        try:
            driver.quit()
        except Exception:
            pass

    return results


def _select_metal(driver, option_value: str):
    select_el = driver.find_element(
        By.CSS_SELECTOR, "select.js-priceswidget-metal"
    )
    Select(select_el).select_by_value(option_value)


def _click_pm(driver):
    pm_btns = driver.find_elements(
        By.CSS_SELECTOR, "button.js-priceswidget-fixing[data-fixing='pm']"
    )
    if not pm_btns:
        raise RuntimeError("Кнопка PM не найдена")

    pm_btn = pm_btns[0]
    classes = pm_btn.get_attribute("class") or ""
    if "bg-blue-bgrad" not in classes:
        pm_btn.click()


def _extract_metal_json(driver, metal_name: str) -> pd.DataFrame:
    """
    Ищет среди свежих network-событий ответ с JSON для нужного металла.
    """
    target_markers = (
        f"{metal_name.lower()}_pm.json",
        f"{metal_name.lower()}.json",
    )

    responses = _collect_responses(driver)
    print(
        f"[LBMA/Selenium] Сетевых ответов от prices.lbma.org.uk: {len(responses)}")

    # Идём в обратном порядке — самые свежие ответы в конце лога
    for request_id, url in reversed(list(responses.items())):
        if not any(marker in url.lower() for marker in target_markers):
            continue

        body = _get_response_body(driver, request_id)
        if not body:
            continue

        try:
            raw_json = json.loads(body)
        except json.JSONDecodeError as e:
            print(f"[LBMA/Selenium] {metal_name}: JSON decode error: {e}")
            continue

        df = _parse_lbma_json(raw_json, metal_name)
        if not df.empty:
            return df

    print(f"[LBMA/Selenium] {metal_name}: подходящий JSON не найден")
    return pd.DataFrame(columns=["Date", metal_name])


def _parse_lbma_json(raw_json, metal_name: str) -> pd.DataFrame:
    if not isinstance(raw_json, list) or not raw_json:
        return pd.DataFrame(columns=["Date", metal_name])

    df = pd.DataFrame(raw_json)
    if "d" not in df.columns or "v" not in df.columns:
        return pd.DataFrame(columns=["Date", metal_name])

    def _first(v):
        if isinstance(v, list):
            return v[0] if v else None
        return v

    df["v"] = df["v"].apply(_first)
    df["d"] = pd.to_datetime(df["d"], errors="coerce")
    df[metal_name] = pd.to_numeric(df["v"], errors="coerce")

    df = df.rename(columns={"d": "Date"})
    df = df[["Date", metal_name]].dropna(subset=["Date"])
    return df.tail(10)


# ================================================================
# Публичный интерфейс (совместим с main.py)
# ================================================================
async def lbma_prescious_async():
    try:
        results = await asyncio.to_thread(_scrape_via_browser)

        gold = results.get("Gold",      pd.DataFrame(columns=["Date", "Gold"]))
        silver = results.get("Silver",    pd.DataFrame(
            columns=["Date", "Silver"]))
        platinum = results.get("Platinum",  pd.DataFrame(
            columns=["Date", "Platinum"]))
        palladium = results.get("Palladium", pd.DataFrame(
            columns=["Date", "Palladium"]))

        if all(df.empty for df in (gold, silver, platinum, palladium)):
            print("[LBMA/Selenium] все ответы пустые — сохранение пропущено")
            return

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

        print("[LBMA/Selenium] is done!!!")

    except Exception as error:
        print(f"[LBMA/Selenium] Произошла ошибка: {error}")
        raise


__all__ = ["lbma_prescious_async"]
