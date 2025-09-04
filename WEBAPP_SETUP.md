Локальный запуск (кратко)

1) Переменные окружения в `.env`:
```
BOT_TOKEN=xxx
WEBAPP_URL=http://localhost:8000
ADMIN_CHANNEL_ID=0
SUPER_ADMIN_IDS=123456789
```

2) Запуск backend API:
```
uvicorn app.main:app --reload --port 8000
```

3) Запуск бота:
```
python -m bot.main
```

4) Открыть mini app из Telegram по кнопке в боте.

