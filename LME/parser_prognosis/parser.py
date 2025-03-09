import aiohttp
import asyncio
import pandas as pd

import warnings
warnings.filterwarnings("ignore")

async def get_data(metall):
    try:
        url = f"https://www.westmetall.com/en/markdaten.php?action=table&field=LME_{metall}_cash"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                text = await response.text()
                df = pd.read_html(text)
                data = df[0]
                # Обработка данных
                data = data[data["date"] != 'date']
                data = data[data.iloc[:, 1] != '-']
                data = data[data.iloc[:, 2] != '-']
                data = data[data.iloc[:, 3] != '-']
                data["date"] = pd.to_datetime(data["date"])
                data.iloc[:, 1] = pd.to_numeric(data.iloc[:, 1])
                data.iloc[:, 2] = pd.to_numeric(data.iloc[:, 2])
                return data
    except Exception as e:
        print(f"Error fetching data for {metall}: {e}")
        return pd.DataFrame()

async def westmetall_async():
    metals = {
        "Al": "aluminium",
        "Cu": "copper",
        "Pb": "lead",
        "Ni": "nickel",
        "Zn": "zink",
        "Sn": "tin"
    }

    for metall, name in metals.items():
        new_data = await get_data(metall)
        if not new_data.empty:
            old_data = pd.read_csv(f"./data/{name}_database.csv")
            combined_data = pd.concat([new_data, old_data]).drop_duplicates()
            combined_data.to_csv(f"./data/{name}_database.csv", index=False)

if __name__ == "__main__":
    print("Parsing starting...")
    
    try:
        # Проверяем, есть ли активный event loop
        loop = asyncio.get_event_loop()
    except RuntimeError:
        # Если нет, создаем новый
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    if loop.is_running():
        # Если event loop уже запущен, используем await
        loop.create_task(westmetall_async())
    else:
        # Если event loop не запущен, используем asyncio.run()
        asyncio.run(westmetall_async())
    
    print("Parsing completed!!!")