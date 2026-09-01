#!/usr/bin/env python3
# parser > lme_parser > lme_parser.py

import asyncio
import warnings
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

warnings.filterwarnings("ignore")

# Привязываем пути к папке lme_parser/data/
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
XLSX_PATH = DATA_DIR / "LME_db_new.xlsx"


def _fetch_lme_data_sync(url: str) -> str:
    """
    Синхронная часть работы с Selenium.
    Выносится отдельно, чтобы запускаться через to_thread.
    """
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
        driver.get(url)
        # Ждем загрузки динамического контента
        import time
        time.sleep(5)

        driver.execute_script(
            "window.scrollTo(0, window.scrollY + window.innerHeight);")
        time.sleep(2)
        driver.execute_script(
            "window.scrollTo(0, window.scrollY + window.innerHeight);")
        time.sleep(3)

        return driver.page_source
    finally:
        driver.quit()


async def lme_selenium_async():
    url = "https://www.lme.com/Metals/Non-ferrous#tabIndex=1"

    try:
        print("🚀 LME parsing started...")

        # Запускаем тяжелый Selenium в отдельном потоке, чтобы не блокировать event loop
        html_code = await asyncio.to_thread(_fetch_lme_data_sync, url)

        soup = BeautifulSoup(html_code, "html.parser")

        # Парсинг данных
        data_raw = soup.find_all("div", class_="metal-block-row__blocks")
        if not data_raw:
            raise ValueError("Не удалось найти блок metal-block-row__blocks")

        metalls_raw = data_raw[0].text
        metalls_raw = metalls_raw.replace(
            " ", "").replace("LME", "LME_").split("\n")
        metalls_raw = " ".join(metalls_raw).strip().split(" ")
        metalls_raw = [metalls_raw[i: i + 4]
                       for i in range(0, len(metalls_raw), 4)]
        metalls_raw = [i[:2] for i in metalls_raw]

        for metall in metalls_raw:
            metall[1] = pd.to_numeric(metall[1], errors="coerce")

        dict_list = [{item[0]: item[1]} for item in metalls_raw]
        metall_df = pd.DataFrame()
        for i in dict_list:
            keys = list(i.keys())
            values = list(i.values())
            metall_df[keys[0]] = values

        # Дропаем ненужные колонки
        drop_cols = ["LME_AluminiumAlloy", "LME_NASAAC"]
        metall_df.drop(
            columns=[c for c in drop_cols if c in metall_df.columns], inplace=True)

        metall_df = metall_df.rename(
            columns={
                "LME_Aluminium": "aluminium",
                "LME_Copper": "copper",
                "LME_Lead": "lead",
                "LME_Nickel": "nickel",
                "LME_Zinc": "zink",
                "LME_Tin": "tin",
            }
        )

        # Дата
        date_raw = soup.find_all(
            "span", class_="metal-block-container__refreshed-on")
        if date_raw:
            date_str = str(date_raw[0]).split(">")[1]
            date_str = date_str.replace("\xa0", "").replace("</span", "")
            quote_date = pd.to_datetime(date_str) - pd.Timedelta(days=1)
        else:
            quote_date = pd.Timestamp.now() - pd.Timedelta(days=1)

        metall_df["date"] = quote_date

        new_column_order = ["date", "aluminium",
                            "copper", "lead", "nickel", "zink", "tin"]
        # Оставляем только существующие колонки
        new_column_order = [
            c for c in new_column_order if c in metall_df.columns]
        metall_df = metall_df[new_column_order]

        # Чтение старого файла
        if XLSX_PATH.exists():
            lme_db = pd.read_excel(XLSX_PATH, index_col=0)
        else:
            lme_db = pd.DataFrame(columns=new_column_order)

        # Объединение и очистка
        lme_db = pd.concat([lme_db, metall_df], ignore_index=True)

        # Дропаем дубликаты по всем колонкам кроме даты (как было в оригинале)
        subset_cols = [c for c in lme_db.columns if c != "date"]
        if subset_cols:
            lme_db = lme_db.drop_duplicates(subset=subset_cols, keep="last")

        lme_db = lme_db.sort_values(by="date").reset_index(drop=True)

        # Сохранение
        with pd.ExcelWriter(
            XLSX_PATH,
            date_format="YYYY-MM-DD",
            datetime_format="YYYY-MM-DD",
        ) as writer:
            lme_db.to_excel(writer, sheet_name="LME_main", index=False)

        print("✅ LME_main is done!!!")

    except Exception as error:
        print(f"❌ LME Error: {error}")


__all__ = ["lme_selenium_async"]
