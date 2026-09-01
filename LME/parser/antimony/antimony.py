#!/usr/bin/env python3
# parser > antimony > antimony.py

import re
from datetime import datetime
from pathlib import Path

import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from bs4 import BeautifulSoup


# Пути привязываем к папке antimony/
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)


# Стандартные имена колонок
COL_DATE = "Date"
COL_USD = "Avg With Rate(USD/mt,VAT included)"
COL_CNY = "Avg(CNY/mt,VAT included)"


def extract_price_after(marker: str, text: str):
    """Извлекает число после указанного маркера."""
    pattern = rf"{re.escape(marker)}\s*([\d,]+\.?\d*)"
    match = re.search(pattern, text)
    return match.group(1).replace(",", "") if match else None


def parse_price_from_html(html_content: str):
    soup = BeautifulSoup(html_content, "html.parser")
    body_text = soup.get_text()

    price_vat_excl = extract_price_after("VAT excluded", body_text)
    price_vat_incl = extract_price_after("VAT included", body_text)
    price_original = extract_price_after("Original", body_text)

    date_pattern = r"([A-Z][a-z]{2,}\s+\d{1,2},\s+\d{4})"
    date_match = re.search(date_pattern, body_text)

    quote_date = (
        date_match.group(1)
        if date_match
        else datetime.now().strftime("%b %d, %Y")
    )

    return {
        "vat_excluded": price_vat_excl,
        "vat_included": price_vat_incl,
        "original": price_original,
        "quote_date": pd.to_datetime(quote_date).date(),
    }


async def antimony_parser():
    options = Options()
    service = Service()

    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--headless")
    options.add_argument("--window-size=1920,1080")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )

    driver = webdriver.Chrome(service=service, options=options)

    try:
        driver.get("https://www-old.metal.com/Antimony/201102250328")

        wait = WebDriverWait(driver, 5)
        wait.until(
            EC.presence_of_element_located(
                (By.XPATH, "//*[contains(text(), 'USD/tonne')]")
            )
        )

        html_content = driver.page_source

        # HTML теперь сохраняется сюда:
        # parser/antimony/data/cnn_data.html
        html_path = DATA_DIR / "cnn_data.html"

        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        result = parse_price_from_html(html_content)

        if not any(
            [
                result["vat_excluded"],
                result["vat_included"],
                result["original"],
            ]
        ):
            raise SystemExit("⚠️ Ни одна цена не найдена. Выход.")

        new_row = pd.DataFrame(
            [
                {
                    COL_DATE: result["quote_date"],
                    COL_USD: result["vat_excluded"],
                    COL_CNY: result["original"],
                }
            ]
        )

        # CSV и Excel теперь тоже в parser/antimony/data/
        csv_path = DATA_DIR / "antimony.csv"

        if csv_path.exists():
            historical = pd.read_csv(csv_path)

            rename_map = {}

            for col in historical.columns:
                if "Date" in col:
                    rename_map[col] = COL_DATE
                elif "Avg With Rate" in col:
                    rename_map[col] = COL_USD
                elif "Avg(CNY" in col:
                    rename_map[col] = COL_CNY

            historical = historical.rename(columns=rename_map)

            historical[COL_DATE] = pd.to_datetime(
                historical[COL_DATE]
            ).dt.date

            updated = pd.concat(
                [historical, new_row],
                ignore_index=True,
            )
        else:
            updated = new_row

        updated = updated.sort_values(COL_DATE).drop_duplicates(
            subset=COL_DATE,
            keep="last",
        )

        updated.to_csv(csv_path, index=False)

        xlsx_path = DATA_DIR / "antimony.xlsx"

        with pd.ExcelWriter(
            xlsx_path,
            date_format="YYYY-MM-DD",
            datetime_format="YYYY-MM-DD",
        ) as writer:
            updated.to_excel(
                writer,
                sheet_name="antimony",
                index=False,
            )

        print("antimony parsing is DONE")

    except Exception as e:
        print(f"❌ Ошибка antimony: {e}")

    finally:
        driver.quit()


__all__ = [
    "antimony_parser",
]
