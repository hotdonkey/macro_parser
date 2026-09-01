#!/usr/bin/env python3
# parser > main.py

import asyncio
import warnings
from pathlib import Path

# Парсеры
from antimony import antimony_parser
from westmetall import westmetall_async
from lme import lme_selenium_async
from lbma import lbma_prescious_async
from cbr import cb_currency, cb_metalls
from nbk import nbk_tenge_async
from shmet import shmet_optimized_async
from kitco import kitco_parser_async

# Сервисные функции из service_layer
from service_layer import (
    read_db,
    show_db,
    db_check,
)

warnings.filterwarnings("ignore")


# ================================================================
# Пути к базам (реальная структура проекта)
# ================================================================
LME_PATH = Path("lme/data/LME_db_new.xlsx")
WESTMETALL_PATH = Path("westmetall/data/LME_westmetall_db.xlsx")

KITCO_PATH = Path("kitco/data/kitko_db.xlsx")
LBMA_PATH = Path("lbma/data/lbma_kitco_subs.xlsx")

ANTIMONY_PATH = Path("antimony/data/antimony.xlsx")

CB_CURRENCY_PATH = Path("cbr/data/cb_currency.xlsx")
CB_METALLS_PATH = Path("cbr/data/cb_metalls.xlsx")

NBK_PATH = Path("nbk/data/nbk_tenge.xlsx")
SHMET_PATH = Path("shmet/data/shmet_historical.xlsx")


# ================================================================
# Основная функция
# ================================================================
async def main():
    print("Parsing started...")

    tasks = {
        "lme": lme_selenium_async(),
        "antimony": antimony_parser(),
        "westmetall": westmetall_async(),
        "lbma": lbma_prescious_async(),
        "kitco": kitco_parser_async(),
        "cb_currency": cb_currency(),
        "cb_metalls": cb_metalls(),
        "nbk": nbk_tenge_async(),
        "shmet": shmet_optimized_async(),
    }

    # return_exceptions=True — чтобы падение одного парсера
    # не останавливало остальные
    results = await asyncio.gather(
        *tasks.values(),
        return_exceptions=True,
    )

    # Проверка результатов
    for name, result in zip(tasks.keys(), results):
        if isinstance(result, Exception):
            print(f"❌ Ошибка в {name}: {result}")

    print("All tasks are done!")
    print("+" * 64)
    print("Checking DB...")

    # Проверка целостности парных баз
    db_check()

    print("DB check completed!")
    print("+" * 64)
    print("Visual control")
    print("+" * 64)

    # Базовые металлы
    show_db("lme_selenium_db", LME_PATH, sheet_name=0)
    show_db("westmetall_db", WESTMETALL_PATH, sheet_name=0)

    # Драгоценные металлы
    show_db("kitco_db", KITCO_PATH, sheet_name=0)
    show_db("lbma_precious_db", LBMA_PATH, sheet_name=0)

    # Антимоний
    show_db("antimony_db", ANTIMONY_PATH, sheet_name=0)

    # ЦБ РФ: валюты (каждая на своем листе)
    for currency in [
        "USD",
        "EUR",
        "British_Pound",
        "China_Yuan",
        "Japanese_Yen",
        "Swiss_Franc",
    ]:
        show_db(
            f"cb_currency ({currency})",
            CB_CURRENCY_PATH,
            sheet_name=currency,
        )

    # ЦБ РФ: металлы
    show_db("cb_metalls_db", CB_METALLS_PATH, sheet_name=0)

    # Казахстан и SHMET
    show_db("nbk_tenge_db", NBK_PATH, sheet_name=0)
    show_db("shmet_historical_db", SHMET_PATH, sheet_name=0, show_head=True)


# ================================================================
# Точка входа
# ================================================================
if __name__ == "__main__":
    asyncio.run(main())
