#!/bin/bash
cd /root/abdu/site

# Генерируем данные
python3 generate_site.py

# Проверяем, изменился ли data.json или index.html
if git diff --quiet data.json index.html; then
    echo "Нет изменений"
    exit 0
fi

git add .
git commit -m "Auto-update $(date +'%Y-%m-%d %H:%M')"
git push origin main
echo "Сайт обновлен"
