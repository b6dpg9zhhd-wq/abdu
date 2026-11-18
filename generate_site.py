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
from datetime import datetime, timedelta, date
from PIL import Image
from config import BOT_TOKEN

DB_PATH = "/root/abdu/sales.db"
REPO_DIR = "/root/abdu/site"

# Сколько дней истории отдавать сайту для стрелок графиков.
HISTORY_DAYS = 400


def get_compliment(name):
    comps = [
        "Гений генераций 🧠", "Машина мощности 🚀", "Король скорости ⚡",
        "Мастер стратегии ♟️", "Звезда чата ⭐", "Легенда генераций 🔥",
        "Просто космос 🌌", "Неудержимый поток 💥", "Топ по мозгам 🧠"
    ]
    h = int(hashlib.md5(name.encode("utf-8")).hexdigest(), 16)
    return comps[h % len(comps)]


def get_avatar(uid, name):
    path = f"{REPO_DIR}/avatars/{uid}.webp"
    if os.path.exists(path):
        return f"avatars/{uid}.webp"

    os.makedirs(f"{REPO_DIR}/avatars", exist_ok=True)
    try:
        url_photos = (
            f"https://api.telegram.org/bot{BOT_TOKEN}/getUserProfilePhotos"
            f"?user_id={uid}&limit=1"
        )
        res = requests.get(url_photos, timeout=10).json()
        if res.get("ok") and res.get("result", {}).get("total_count", 0) > 0:
            file_id = res["result"]["photos"][0][-1]["file_id"]
            res2 = requests.get(
                f"https://api.telegram.org/bot{BOT_TOKEN}/getFile",
                params={"file_id": file_id},
                timeout=10
            ).json()
            if res2.get("ok"):
                img_url = (
                    "https://api.telegram.org/file/bot"
                    f"{BOT_TOKEN}/{res2['result']['file_path']}"
                )
                img_bytes = requests.get(img_url, timeout=15).content
                img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
                img.thumbnail((128, 128))
                img.save(path, format="WEBP", quality=80)
                return f"avatars/{uid}.webp"
    except Exception:
        pass

    colors = ["#FF512F", "#1FA2FF", "#F09819", "#8E2DE2", "#00B4DB"]
    # Не используем встроенный hash(): он меняется между запусками Python.
    color_index = int(hashlib.md5(name.encode("utf-8")).hexdigest(), 16) % len(colors)
    img = Image.new("RGB", (128, 128), color=colors[color_index])
    img.save(path, format="WEBP", quality=80)
    return f"avatars/{uid}.webp"


def get_graph_data(con, table, metric, period, anchor_date=None):
    """График периода, заканчивающегося в anchor_date."""
    anchor_date = anchor_date or datetime.now().date()

    if period == "today":
        start = datetime.combine(anchor_date, datetime.min.time())
        end = start + timedelta(days=1)
        rows = con.execute(
            f"""
            SELECT CAST(strftime('%H', ts) AS INTEGER) AS bucket,
                   COALESCE(SUM({metric}), 0)
            FROM {table}
            WHERE ts >= ? AND ts < ?
            GROUP BY bucket
            """,
            (start.isoformat(), end.isoformat())
        ).fetchall()

        totals = {int(row[0]): int(row[1] or 0) for row in rows}
        return {
            "labels": [f"{hour:02d}:00" for hour in range(24)],
            "values": [totals.get(hour, 0) for hour in range(24)]
        }

    days = 7 if period == "week" else 30
    first_day = anchor_date - timedelta(days=days - 1)
    start = datetime.combine(first_day, datetime.min.time())
    end = datetime.combine(anchor_date + timedelta(days=1), datetime.min.time())

    rows = con.execute(
        f"""
        SELECT DATE(ts) AS bucket, COALESCE(SUM({metric}), 0)
        FROM {table}
        WHERE ts >= ? AND ts < ?
        GROUP BY DATE(ts)
        """,
        (start.isoformat(), end.isoformat())
    ).fetchall()

    totals = {row[0]: int(row[1] or 0) for row in rows}
    labels = [
        (first_day + timedelta(days=i)).strftime("%d.%m")
        for i in range(days)
    ]
    values = [
        totals.get((first_day + timedelta(days=i)).isoformat(), 0)
        for i in range(days)
    ]
    return {"labels": labels, "values": values}


def get_calendar_data(con, offset_months=0):
    now = datetime.now()
    year, month = now.year, now.month + offset_months

    while month <= 0:
        month += 12
        year -= 1
    while month > 12:
        month -= 12
        year += 1

    first_day = datetime(year, month, 1)
    _, days_in_month = calendar.monthrange(year, month)
    next_month = (
        datetime(year + 1, 1, 1)
        if month == 12 else datetime(year, month + 1, 1)
    )

    rows = con.execute(
        """
        SELECT DATE(ts), COALESCE(SUM(count), 0)
        FROM sales
        WHERE ts >= ? AND ts < ?
        GROUP BY DATE(ts)
        """,
        (first_day.isoformat(), next_month.isoformat())
    ).fetchall()

    day_counts = {row[0]: int(row[1] or 0) for row in rows}
    max_val = max(day_counts.values()) if day_counts else 0

    days = [
        {"day": None, "count": 0, "color": None, "level": 0, "is_today": False}
        for _ in range(first_day.weekday())
    ]

    for day in range(1, days_in_month + 1):
        date_str = f"{year}-{month:02d}-{day:02d}"
        count = day_counts.get(date_str, 0)
        ratio = count / max_val if max_val else 0
        level = 0 if count == 0 else min(4, max(1, int(ratio * 4) + 1))
        color = (
            "gray" if level == 0 else
            "red" if level == 1 else
            "orange" if level == 2 else
            "yellow" if level == 3 else "green"
        )
        days.append({
            "day": day,
            "count": count,
            "color": color,
            "level": level,
            "is_today": (
                year == now.year and month == now.month and day == now.day
            )
        })

    while len(days) < 42:
        days.append({
            "day": None, "count": 0, "color": None,
            "level": 0, "is_today": False
        })

    return {
        "title": first_day.strftime("%B %Y").capitalize(),
        "days": days,
        "max": max_val
    }


def build_graph_history(con, now_date):
    """
    Создаёт историю для переключения стрелками.
    Ключи имеют формат today:YYYY-MM-DD, week:YYYY-MM-DD,
    month:YYYY-MM-DD. Также сохраняется короткий ключ YYYY-MM-DD.
    """
    history = {}

    for offset in range(HISTORY_DAYS):
        anchor = now_date - timedelta(days=offset)
        date_key = anchor.isoformat()

        day_graphs = {
            "sales": get_graph_data(con, "sales", "count", "today", anchor),
            "milk": get_graph_data(con, "milk", "count", "today", anchor),
            "tasks": get_graph_data(con, "tasks", "money", "today", anchor)
        }
        week_graphs = {
            "sales": get_graph_data(con, "sales", "count", "week", anchor),
            "milk": get_graph_data(con, "milk", "count", "week", anchor),
            "tasks": get_graph_data(con, "tasks", "money", "week", anchor)
        }
        month_graphs = {
            "sales": get_graph_data(con, "sales", "count", "month", anchor),
            "milk": get_graph_data(con, "milk", "count", "month", anchor),
            "tasks": get_graph_data(con, "tasks", "money", "month", anchor)
        }

        history[date_key] = {"date": date_key, "graphs": day_graphs}
        history[f"today:{date_key}"] = {
            "date": date_key, "graphs": day_graphs
        }
        history[f"week:{date_key}"] = {
            "date": date_key, "graphs": week_graphs
        }
        history[f"month:{date_key}"] = {
            "date": date_key, "graphs": month_graphs
        }

    return history


def get_data():
    con = sqlite3.connect(DB_PATH)
    try:
        now = datetime.now()
        now_date = now.date()

        periods = {
            "today": now.replace(
                hour=0, minute=0, second=0, microsecond=0
            ).isoformat(),
            "week": (now - timedelta(days=7)).isoformat(),
            "month": (now - timedelta(days=30)).isoformat(),
            "all": datetime(2000, 1, 1).isoformat()
        }

        data = {}

        for p_name, since in periods.items():
            sales = con.execute(
                """
                SELECT b.nickname, b.username, s.buyer_id,
                       SUM(s.count) AS total
                FROM sales s
                LEFT JOIN buyers b ON b.buyer_id = s.buyer_id
                WHERE s.ts >= ?
                GROUP BY s.buyer_id
                HAVING total > 0
                ORDER BY total DESC
                LIMIT 10
                """,
                (since,)
            ).fetchall()

            tasks = con.execute(
                """
                SELECT resource,
                       COALESCE(SUM(amount), 0),
                       COALESCE(SUM(money), 0)
                FROM tasks
                WHERE ts >= ?
                GROUP BY resource
                ORDER BY COALESCE(SUM(money), 0) DESC
                LIMIT 6
                """,
                (since,)
            ).fetchall()

            milk = con.execute(
                """
                SELECT b.nickname, b.username, m.user_id,
                       SUM(m.count) AS total
                FROM milk m
                LEFT JOIN buyers b ON b.buyer_id = m.user_id
                WHERE m.ts >= ?
                GROUP BY m.user_id
                HAVING total > 0
                ORDER BY total DESC
                LIMIT 10
                """,
                (since,)
            ).fetchall()

            totals = con.execute(
                """
                SELECT
                    (SELECT COALESCE(SUM(count), 0) FROM sales WHERE ts >= ?),
                    (SELECT COALESCE(SUM(count), 0) FROM milk WHERE ts >= ?),
                    (SELECT COALESCE(SUM(money), 0) FROM tasks WHERE ts >= ?)
                """,
                (since, since, since)
            ).fetchone()

            task_items = []
            for row in tasks:
                amount = int(row[1] or 0)
                earned = int(row[2] or 0)
                task_items.append({
                    "name": row[0] or "Ресурс",
                    "amount": amount,
                    "money": earned,
                    "earned": earned,
                    "profit": earned
                })

            data[p_name] = {
                "sales": [
                    {
                        "name": r[0] or r[1] or f"id{r[2]}",
                        "val": int(r[3] or 0),
                        "uid": r[2],
                        "ava": get_avatar(
                            r[2], r[0] or r[1] or ""
                        )
                    }
                    for r in sales
                ],
                "tasks": task_items,
                "sales_total": int(totals[0] or 0),
                "milk_total": int(totals[1] or 0),
                "tasks_money_total": int(totals[2] or 0),
                "milk": [
                    {
                        "name": r[0] or r[1] or f"id{r[2]}",
                        "val": int(r[3] or 0),
                        "uid": r[2],
                        "ava": get_avatar(
                            r[2], r[0] or r[1] or ""
                        )
                    }
                    for r in milk
                ],
                "graph": get_graph_data(
                    con, "sales", "count", p_name, now_date
                ),
                "graphs": {
                    "sales": get_graph_data(
                        con, "sales", "count", p_name, now_date
                    ),
                    "milk": get_graph_data(
                        con, "milk", "count", p_name, now_date
                    ),
                    "tasks": get_graph_data(
                        con, "tasks", "money", p_name, now_date
                    )
                },
                "calendar": get_calendar_data(con, 0)
            }

        # История графиков для перелистывания назад/вперёд.
        data["history"] = build_graph_history(con, now_date)

        # История календаря: текущий и 23 предыдущих месяца.
        calendar_history = {}
        for month_offset in range(-23, 1):
            cal = get_calendar_data(con, month_offset)
            month_date = now.replace(day=1) + timedelta(days=month_offset * 31)
            # Ключ вычисляем календарно, без ошибок на границах месяцев.
            month_index = now.year * 12 + (now.month - 1) + month_offset
            cal_year, cal_month_zero = divmod(month_index, 12)
            cal_key = f"{cal_year}-{cal_month_zero + 1:02d}"
            cal["total"] = sum(int(day.get("count", 0) or 0) for day in cal["days"])
            calendar_history[cal_key] = cal
        data["calendar_history"] = calendar_history

        # Подробный журнал операций: до 1 000 строк на источник.
        logs = []

        sales_rows = con.execute("""
            SELECT s.ts,
                   COALESCE(b.nickname, b.username, 'id' || s.buyer_id),
                   s.count, s.buyer_id
            FROM sales s
            LEFT JOIN buyers b ON b.buyer_id = s.buyer_id
            ORDER BY s.ts DESC
            LIMIT 1000
        """).fetchall()

        for ts, name, amount, uid in sales_rows:
            logs.append({
                "ts": ts,
                "type": "sales",
                "typeLabel": "💎 Генки",
                "name": name,
                "detail": "Генерация",
                "amount": int(amount or 0),
                "money": 0
            })

        milk_rows = con.execute("""
            SELECT m.ts,
                   COALESCE(b.nickname, b.username, 'id' || m.user_id),
                   m.count, m.user_id
            FROM milk m
            LEFT JOIN buyers b ON b.buyer_id = m.user_id
            ORDER BY m.ts DESC
            LIMIT 1000
        """).fetchall()

        for ts, name, amount, uid in milk_rows:
            logs.append({
                "ts": ts,
                "type": "milk",
                "typeLabel": "🥛 Дойка",
                "name": name,
                "detail": "Дойка",
                "amount": int(amount or 0),
                "money": 0
            })

        task_rows = con.execute("""
            SELECT ts, COALESCE(worker, '—'), resource, amount, money
            FROM tasks
            ORDER BY ts DESC
            LIMIT 1000
        """).fetchall()

        for ts, name, resource, amount, money in task_rows:
            earned = int(money or 0)
            logs.append({
                "ts": ts,
                "type": "tasks",
                "typeLabel": "📦 Таски",
                "name": name,
                "detail": str(resource or "Ресурс"),
                "amount": int(amount or 0),
                "money": earned,
                "earned": earned
            })

        logs.sort(
            key=lambda item: item.get("ts") or "",
            reverse=True
        )
        data["logs"] = logs[:2000]

        return data
    finally:
        con.close()


if __name__ == "__main__":
    os.makedirs(REPO_DIR, exist_ok=True)
    result = get_data()
    output_path = f"{REPO_DIR}/data.json"

    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(result, file, ensure_ascii=False)

    print(
        f"OK: data.json обновлён; "
        f"история графиков: {HISTORY_DAYS} дней"
    )
