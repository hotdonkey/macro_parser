import requests

url = "https://api.db.nomics.world/v22/series?provider_code=LBMA&limit=1000"
response = requests.get(url, timeout=30)
data = response.json()
series_list = data.get("series", {}).get("docs", [])

print(f"Всего серий найдено: {len(series_list)}")
for series in series_list[:20]:  # Показать первые 20
    print(f"  {series['series_code']}: {series['series_name']}")
