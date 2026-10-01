# # check_lbma.py
# import asyncio
# import httpx

# HEADERS = {
#     "User-Agent": (
#         "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
#         "AppleWebKit/537.36 (KHTML, like Gecko) "
#         "Chrome/124.0.0.0 Safari/537.36"
#     ),
#     "Accept": "application/json, text/plain, */*",
#     "Accept-Language": "en-US,en;q=0.9",
#     "Referer": "https://www.lbma.org.uk/prices-and-data",
#     "Origin": "https://www.lbma.org.uk",
# }


# async def main():
#     async with httpx.AsyncClient(
#         headers=HEADERS, http2=True, follow_redirects=True, timeout=30
#     ) as c:
#         r = await c.get("https://prices.lbma.org.uk/json/gold_pm.json")
#         print("status:", r.status_code)
#         print("http_version:", r.http_version)
#         print("server:", r.headers.get("server"))
#         print("cf-ray:", r.headers.get("cf-ray"))
#         print("body[:300]:", r.text[:300])

# asyncio.run(main())

# -------------------------------
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
        print("ja3-профиль:", "chrome124")
        print("server:", r.headers.get("server"))
        print("cf-ray:", r.headers.get("cf-ray"))
        print("body[:300]:", r.text[:300])

asyncio.run(main())
