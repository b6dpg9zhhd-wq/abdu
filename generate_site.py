import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sqlite3
import requests
import base64
import io
import hashlib
import json
from datetime import datetime, timedelta
from PIL import Image
from config import BOT_TOKEN

DB_PATH = "/root/abdu/sales.db"
REPO_DIR = "/root/abdu/site"

def get_compliment(name):
    comps = ["Гений генераций 🧠", "Машина мощности 🚀", "Король скорости ⚡", "Мастер стратегии ♟️", "Звезда чата ⭐", "Легенда генераций 🔥", "Просто космос 🌌", "Неудержимый поток 💥", "Топ по мозгам 🧠"]
    h = int(hashlib.md5(name.encode('utf-8')).hexdigest(), 16)
    return comps[h % len(comps)]

def get_avatar(uid, name):
    path = f"{REPO_DIR}/avatars/{uid}.webp"
    if os.path.exists(path):
        return f"avatars/{uid}.webp"
    
    os.makedirs(f"{REPO_DIR}/avatars", exist_ok=True)
    try:
        url_photos = f'https://api.telegram.org/bot{BOT_TOKEN}/getUserProfilePhotos?user_id={uid}&limit=1'
        res = requests.get(url_photos).json()
        if res.get('ok') and res.get('result', {}).get('total_count', 0) > 0:
            file_id = res['result']['photos'][0][-1]['file_id']
            res2 = requests.get(f'https://api.telegram.org/bot{BOT_TOKEN}/getFile?file_id={file_id}').json()
            if res2.get('ok'):
                img_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{res2['result']['file_path']}"
                img_bytes = requests.get(img_url).content
                img = Image.open(io.BytesIO(img_bytes)).convert('RGB')
                img.thumbnail((128, 128))
                img.save(path, format='WEBP', quality=80)
                return f"avatars/{uid}.webp"
    except: pass
    
    # Заглушка, если авы нет
    colors = ['#FF512F', '#1FA2FF', '#F09819', '#8E2DE2', '#00B4DB']
    img = Image.new('RGB', (128, 128), color=colors[hash(name) % len(colors)])
    img.save(path, format='WEBP', quality=80)
    return f"avatars/{uid}.webp"

def get_data():
    con = sqlite3.connect(DB_PATH)
    now = datetime.now()
    periods = {
        "today": now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat(),
        "week": (now - timedelta(days=7)).isoformat(),
        "month": (now - timedelta(days=30)).isoformat(),
        "all": datetime(2000, 1, 1).isoformat()
    }

    data = {}
    for p_name, since in periods.items():
        # Генки
        sales = con.execute("""
            SELECT b.nickname, b.username, s.buyer_id, SUM(s.count) as total 
            FROM sales s LEFT JOIN buyers b ON b.buyer_id = s.buyer_id 
            WHERE s.ts >= ? GROUP BY s.buyer_id HAVING total > 0 ORDER BY total DESC LIMIT 5
        """, (since,)).fetchall()
        
        # Таски
        tasks = con.execute("""
            SELECT resource, SUM(amount), SUM(money) 
            FROM tasks WHERE ts >= ? GROUP BY resource ORDER BY SUM(money) DESC LIMIT 5
        """, (since,)).fetchall()
        
        # Молоко
        milk = con.execute("""
            SELECT b.nickname, b.username, m.user_id, SUM(m.count) as total 
            FROM milk m LEFT JOIN buyers b ON b.buyer_id = m.user_id 
            WHERE m.ts >= ? GROUP BY m.user_id HAVING total > 0 ORDER BY total DESC LIMIT 5
        """, (since,)).fetchall()

        data[p_name] = {
            "sales": [{"name": r[0] or r[1] or f"id{r[2]}", "val": int(r[3]), "uid": r[2], "ava": get_avatar(r[2], r[0] or r[1] or "")} for r in sales],
            "tasks": [{"name": r[0], "amount": int(r[1]), "money": int(r[2])} for r in tasks],
            "milk": [{"name": r[0] or r[1] or f"id{r[2]}", "val": int(r[3]), "uid": r[2], "ava": get_avatar(r[2], r[0] or r[1] or "")} for r in milk]
        }
    con.close()
    return data

# Сохраняем в data.json
data = get_data()
with open(f"{REPO_DIR}/data.json", "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False)

print("OK: data.json обновлен (с аватарками)")
