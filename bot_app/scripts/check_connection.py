# check_connection.py
import os
import requests
import socket
from dotenv import load_dotenv

load_dotenv()
token = os.getenv('BOT_TOKEN')
if not token:
    raise SystemExit('BOT_TOKEN не задан')
url = f"https://api.telegram.org/bot{token}/getMe"

try:
    socket.gethostbyname('api.telegram.org')
    print("✅ DNS работает")
    response = requests.get(url, timeout=10)
    print(f"✅ Статус: {response.status_code}")
    print(f"Ответ: {response.json()}")
except Exception as e:
    print(f"❌ Ошибка: {e}")