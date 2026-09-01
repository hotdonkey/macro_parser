#!/usr/bin/env python3
# parser > main.py

import asyncio

from antimony import antimony_parser
from westmetall import westmetall_async
from lme import lme_selenium_async
from lbma import lbma_prescious_async
from cbr import cb_currency, cb_metalls
from nbk import nbk_tenge_async
from shmet import shmet_optimized_async
from kitco import kitco_parser_async


async def main():
    print("Parsing started...")

    await asyncio.gather(
        lme_selenium_async(),
        antimony_parser(),
        westmetall_async(),
        lbma_prescious_async(),
        cb_currency(),
        cb_metalls(),
        nbk_tenge_async(),
        shmet_optimized_async(),
    )

    print("All tasks are done!")
    print("++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++")
    print("++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++")


if __name__ == "__main__":
    asyncio.run(main())
