import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sqlite3
import json
import os
import hashlib
from datetime import datetime, timedelta
from config import DB_PATH

REPO_DIR = "/root/abdu/site"

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
            "sales": [{"name": r[0] or r[1] or f"id{r[2]}", "val": int(r[3]), "uid": r[2]} for r in sales],
            "tasks": [{"name": r[0], "amount": int(r[1]), "money": int(r[2])} for r in tasks],
            "milk": [{"name": r[0] or r[1] or f"id{r[2]}", "val": int(r[3]), "uid": r[2]} for r in milk]
        }
    con.close()
    return data

# Сохраняем в data.json
data = get_data()
with open(f"{REPO_DIR}/data.json", "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False)

print("OK: data.json обновлен")
