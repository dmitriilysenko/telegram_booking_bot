# check_connection.py
import requests
import socket

TOKEN = "8496786256:AAEFyL2YRx8ST_P5-6yCNsViSc81VBL8Gzw"
url = f"https://api.telegram.org/bot{TOKEN}/getMe"

try:
    print("Проверяем DNS...")
    socket.gethostbyname('api.telegram.org')
    print("✅ DNS работает")

    print("Проверяем подключение через requests...")
    response = requests.get(url, timeout=10)
    print(f"✅ Статус: {response.status_code}")
    print(f"Ответ: {response.json()}")
except Exception as e:
    print(f"❌ Ошибка: {e}")