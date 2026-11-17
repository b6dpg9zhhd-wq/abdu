import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sqlite3
import requests
import base64
import io
import hashlib
import json
import calendar
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
    
    colors = ['#FF512F', '#1FA2FF', '#F09819', '#8E2DE2', '#00B4DB']
    img = Image.new('RGB', (128, 128), color=colors[hash(name) % len(colors)])
    img.save(path, format='WEBP', quality=80)
    return f"avatars/{uid}.webp"

def get_graph_data(con, table, metric, period):
    """Return exact daily/hourly totals for one dashboard metric."""
    now = datetime.now()
    if period == "today":
        since = now.replace(hour=0, minute=0, second=0, microsecond=0)
        rows = con.execute(
            f"SELECT strftime('%H', ts) AS bucket, COALESCE(SUM({metric}), 0) FROM {table} WHERE ts >= ? GROUP BY bucket",
            (since.isoformat(),)
        ).fetchall()
        totals = {int(row[0]): int(row[1] or 0) for row in rows}
        labels = [f"{hour:02d}:00" for hour in range(24)]
        values = [totals.get(hour, 0) for hour in range(24)]
    else:
        days = 7 if period == "week" else 30
        since = (now - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
        rows = con.execute(
            f"SELECT DATE(ts) AS bucket, COALESCE(SUM({metric}), 0) FROM {table} WHERE ts >= ? GROUP BY bucket",
            (since.isoformat(),)
        ).fetchall()
        totals = {row[0]: int(row[1] or 0) for row in rows}
        labels = [(since + timedelta(days=i)).strftime("%d.%m") for i in range(days)]
        values = [totals.get((since + timedelta(days=i)).strftime("%Y-%m-%d"), 0) for i in range(days)]
    return {"labels": labels, "values": values}

def get_calendar_data(con, offset_months=0):
    now = datetime.now()
    year, month = now.year, now.month + offset_months
    while month <= 0:
        month += 12; year -= 1
    while month > 12:
        month -= 12; year += 1
    first_day = datetime(year, month, 1)
    _, days_in_month = calendar.monthrange(year, month)
    next_month = datetime(year + 1, 1, 1) if month == 12 else datetime(year, month + 1, 1)
    rows = con.execute(
        "SELECT DATE(ts), COALESCE(SUM(count), 0) FROM sales WHERE ts >= ? AND ts < ? GROUP BY DATE(ts)",
        (first_day.isoformat(), next_month.isoformat())
    ).fetchall()
    day_counts = {row[0]: int(row[1] or 0) for row in rows}
    max_val = max(day_counts.values()) if day_counts else 0
    days = [{"day": None, "count": 0, "color": None, "level": 0, "is_today": False} for _ in range(first_day.weekday())]
    for day in range(1, days_in_month + 1):
        date_str = f"{year}-{month:02d}-{day:02d}"
        count = day_counts.get(date_str, 0)
        ratio = count / max_val if max_val else 0
        level = 0 if count == 0 else min(4, max(1, int(ratio * 4) + 1))
        color = "gray" if level == 0 else ("red" if level == 1 else "orange" if level == 2 else "yellow" if level == 3 else "green")
        days.append({"day": day, "count": count, "color": color, "level": level,
                     "is_today": year == now.year and month == now.month and day == now.day})
    while len(days) < 42:
        days.append({"day": None, "count": 0, "color": None, "level": 0, "is_today": False})
    return {"title": first_day.strftime("%B %Y").capitalize(), "days": days, "max": max_val}

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
        sales = con.execute("SELECT b.nickname, b.username, s.buyer_id, SUM(s.count) as total FROM sales s LEFT JOIN buyers b ON b.buyer_id = s.buyer_id WHERE s.ts >= ? GROUP BY s.buyer_id HAVING total > 0 ORDER BY total DESC LIMIT 5", (since,)).fetchall()
        tasks = con.execute("SELECT resource, SUM(amount), SUM(money) FROM tasks WHERE ts >= ? GROUP BY resource ORDER BY SUM(money) DESC LIMIT 5", (since,)).fetchall()
        milk = con.execute("SELECT b.nickname, b.username, m.user_id, SUM(m.count) as total FROM milk m LEFT JOIN buyers b ON b.buyer_id = m.user_id WHERE m.ts >= ? GROUP BY m.user_id HAVING total > 0 ORDER BY total DESC LIMIT 5", (since,)).fetchall()

        data[p_name] = {
            "sales": [{"name": r[0] or r[1] or f"id{r[2]}", "val": int(r[3]), "uid": r[2], "ava": get_avatar(r[2], r[0] or r[1] or "")} for r in sales],
            "tasks": [{"name": r[0], "amount": int(r[1]), "money": int(r[2])} for r in tasks],
            "milk": [{"name": r[0] or r[1] or f"id{r[2]}", "val": int(r[3]), "uid": r[2], "ava": get_avatar(r[2], r[0] or r[1] or "")} for r in milk],
            "graph": get_graph_data(con, "sales", "count", p_name),
            "graphs": {
                "sales": get_graph_data(con, "sales", "count", p_name),
                "milk": get_graph_data(con, "milk", "count", p_name),
                "tasks": get_graph_data(con, "tasks", "money", p_name)
            },
            "calendar": get_calendar_data(con, 0)
        }
    # Detailed operation journal for the website (latest 1,000 rows per source).
    logs = []
    sales_rows = con.execute("""
        SELECT s.ts, COALESCE(b.nickname, b.username, 'id' || s.buyer_id),
               s.count, s.buyer_id
        FROM sales s LEFT JOIN buyers b ON b.buyer_id = s.buyer_id
        ORDER BY s.ts DESC LIMIT 1000
    """).fetchall()
    for ts, name, amount, uid in sales_rows:
        logs.append({"ts": ts, "type": "sales", "typeLabel": "💎 Генки",
                     "name": name, "detail": "Генерация", "amount": int(amount or 0), "money": 0})

    milk_rows = con.execute("""
        SELECT m.ts, COALESCE(b.nickname, b.username, 'id' || m.user_id),
               m.count, m.user_id
        FROM milk m LEFT JOIN buyers b ON b.buyer_id = m.user_id
        ORDER BY m.ts DESC LIMIT 1000
    """).fetchall()
    for ts, name, amount, uid in milk_rows:
        logs.append({"ts": ts, "type": "milk", "typeLabel": "🥛 Дойка",
                     "name": name, "detail": "Дойка", "amount": int(amount or 0), "money": 0})

    task_rows = con.execute("""
        SELECT ts, COALESCE(worker, '—'), resource, amount, money
        FROM tasks ORDER BY ts DESC LIMIT 1000
    """).fetchall()
    for ts, name, resource, amount, money in task_rows:
        logs.append({"ts": ts, "type": "tasks", "typeLabel": "📦 Таски",
                     "name": name, "detail": str(resource or "Ресурс"),
                     "amount": int(amount or 0), "money": int(money or 0)})

    logs.sort(key=lambda item: item.get("ts") or "", reverse=True)
    data["logs"] = logs[:2000]
    con.close()
    return data

data = get_data()
with open(f"{REPO_DIR}/data.json", "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False)

print("OK: data.json обновлен (с графиками и календарем)")
