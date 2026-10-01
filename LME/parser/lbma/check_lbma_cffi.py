# check_lbma_cffi.py
import asyncio
from curl_cffi.requests import AsyncSession


async def main():
    async with AsyncSession() as s:
        r = await s.get(
            "https://prices.lbma.org.uk/json/gold_pm.json",
            impersonate="chrome124",
            timeout=30,
        )
        print("status:", r.status_code)
        print("cf-mitigated:", r.headers.get("cf-mitigated"))
        print("server:", r.headers.get("server"))
        print("set-cookie:", r.headers.get("set-cookie"))
        body = r.text
        for marker in ["cf-chl", "turnstile", "Just a moment",
                       "__cf_chl", "challenge-platform", "cf_clearance"]:
            if marker.lower() in body.lower():
                print(f"  ← найден маркер: {marker}")
        # Сохрани для анализа
        with open("cf_response.html", "w") as f:
            f.write(body)
        print("body сохранён в cf_response.html")

asyncio.run(main())
