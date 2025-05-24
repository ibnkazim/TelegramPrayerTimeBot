import asyncio
import requests
from bs4 import BeautifulSoup
import schedule
from datetime import datetime, timezone, timedelta
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from fastapi import FastAPI, Request, Response
from http import HTTPStatus
import json
import os
import logging
import sys

# Настройка логирования в консоль
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

# Конфигурация
BOT_TOKEN = os.getenv("BOT_TOKEN")
PRAYER_URL = "https://qmdi.ru/raspisanie-namazov/"
SUBSCRIBERS_FILE = "subscribers.json"

# Проверка переменных окружения
logging.info("Проверка переменных окружения: BOT_TOKEN=%s, WEBHOOK_URL=%s", 
             "set" if BOT_TOKEN else "not set", os.getenv("WEBHOOK_URL"))

# Инициализация FastAPI
app = FastAPI()

# Инициализация бота
ptb = Application.builder().token(BOT_TOKEN).updater(None).build()

# Хранилище расписания намаза и подписчиков
prayer_times = {}
subscribers = set()

def load_subscribers():
    """Загрузка подписчиков из файла"""
    global subscribers
    logging.info("Загрузка подписчиков из %s", SUBSCRIBERS_FILE)
    try:
        if os.path.exists(SUBSCRIBERS_FILE):
            with open(SUBSCRIBERS_FILE, "r") as f:
                subscribers = set(json.load(f))
            logging.info("Подписчики загружены: %s", subscribers)
        else:
            logging.info("Файл подписчиков не существует")
    except Exception as e:
        logging.error("Ошибка загрузки подписчиков: %s", e)
    return subscribers

def save_subscribers():
    """Сохранение подписчиков в файл"""
    logging.info("Сохранение подписчиков в %s", SUBSCRIBERS_FILE)
    try:
        os.makedirs(os.path.dirname(SUBSCRIBERS_FILE), exist_ok=True)
        with open(SUBSCRIBERS_FILE, "w") as f:
            json.dump(list(subscribers), f)
        logging.info("Подписчики сохранены: %s", subscribers)
    except Exception as e:
        logging.error("Ошибка сохранения подписчиков: %s", e)

async def fetch_prayer_times():
    """Получение времени намаза с сайта qmdi.ru"""
    logging.info("Начало парсинга расписания с %s", PRAYER_URL)
    try:
        response = requests.get(PRAYER_URL)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        
        table = soup.find("table")
        if not table:
            logging.error("Таблица не найдена")
            return False
        
        rows = table.find_all("tr")[1:]
        today = datetime.now(timezone(timedelta(hours=3))).strftime("%d.%m.%Y")  # MSK
        logging.info("Проверяем дату: %s", today)
        
        for row in rows:
            cells = row.find_all("td")
            if len(cells) >= 6 and cells[0].text.strip() == today:
                prayer_times.update({
                    "Фаджр": cells[1].text.strip(),
                    "Зухр": cells[2].text.strip(),
                    "Аср": cells[3].text.strip(),
                    "Магриб": cells[4].text.strip(),
                    "Иша": cells[5].text.strip()
                })
                logging.info("Расписание найдено: %s", prayer_times)
                return True
        logging.warning("Расписание на %s не найдено", today)
        return False
    except Exception as e:
        logging.error("Ошибка парсинга: %s", e)
        return False

async def send_prayer_notification(context: ContextTypes.DEFAULT_TYPE, prayer_name: str, prayer_time: str):
    """Отправка уведомления о намазе всем подписчикам"""
    now = datetime.now(timezone(timedelta(hours=3))).strftime("%H:%M")  # MSK
    message = f"Время намаза {prayer_name}: {prayer_time} (MSK: {now})"
    logging.info("Отправка уведомления: %s, подписчики: %s", message, subscribers)
    for chat_id in subscribers:
        try:
            await context.bot.send_message(chat_id=chat_id, text=message)
            logging.info("Уведомление отправлено %s: %s", chat_id, message)
        except Exception as e:
            logging.error("Ошибка при отправке %s: %s", chat_id, e)

def schedule_prayer_notifications():
    """Планирование уведомлений"""
    schedule.clear()
    logging.info("Планирование уведомлений")
    for prayer, time_str in prayer_times.items():
        schedule.every().day.at(time_str).do(
            lambda p=prayer, t=time_str: ptb.create_task(send_prayer_notification(ptb, p, t))
        )
        logging.info("Запланировано: %s на %s", prayer, time_str)
    logging.info("Все уведомления запланированы: %s", prayer_times)

async def update_prayer_times_daily():
    """Ежедневное обновление расписания"""
    logging.info("Ежедневное обновление расписания")
    if await fetch_prayer_times():
        schedule_prayer_notifications()
    else:
        logging.error("Не удалось обновить расписание")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка команды /start"""
    chat_id = update.effective_chat.id
    logging.info("Команда /start от %s", chat_id)
    if chat_id not in subscribers:
        subscribers.add(chat_id)
        save_subscribers()
        await update.message.reply_text("Вы подписались на уведомления о намазе!")
        logging.info("Новый подписчик: %s", chat_id)
    else:
        await update.message.reply_text("Вы уже подписаны на уведомления.")
        logging.info("Повторная подписка: %s", chat_id)

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка команды /stop"""
    chat_id = update.effective_chat.id
    logging.info("Команда /stop от %s", chat_id)
    if chat_id in subscribers:
        subscribers.remove(chat_id)
        save_subscribers()
        await update.message.reply_text("Вы отписались от уведомлений.")
        logging.info("Подписчик отписался: %s", chat_id)
    else:
        await update.message.reply_text("Вы не подписаны на уведомления.")
        logging.info("Попытка отписки неподписанного: %s", chat_id)

# FastAPI webhook endpoint
@app.post("/")
async def process_update(request: Request):
    """Обработка входящих обновлений от Telegram"""
    logging.info("Получен webhook-запрос")
    try:
        req = await request.json()
        update = Update.de_json(req, ptb.bot)
        if update:
            await ptb.process_update(update)
            logging.info("Webhook обработан успешно")
        return Response(status_code=HTTPStatus.OK)
    except Exception as e:
        logging.error("Ошибка обработки webhook: %s", e)
        return Response(status_code=HTTPStatus.BAD_REQUEST)

# Debug endpoints
@app.get("/subscribers")
async def get_subscribers():
    """Отладка: список подписчиков"""
    logging.info("Запрос списка подписчиков")
    return {"subscribers": list(subscribers)}

@app.get("/env")
async def get_env():
    """Отладка: переменные окружения"""
    logging.info("Запрос переменных окружения")
    return {
        "BOT_TOKEN": "set" if os.getenv("BOT_TOKEN") else "not set",
        "WEBHOOK_URL": os.getenv("WEBHOOK_URL"),
        "PORT": os.getenv("PORT")
    }

# FastAPI lifespan для настройки webhook
@app.on_event("startup")
async def on_startup():
    """Настройка webhook и запуск бота"""
    logging.info("Запуск бота")
    try:
        load_subscribers()
        await fetch_prayer_times()
        schedule_prayer_notifications()
        schedule.every().day.at("00:01").do(
            lambda: ptb.create_task(update_prayer_times_daily())
        )
        webhook_url = os.getenv("WEBHOOK_URL")
        if not webhook_url:
            logging.error("WEBHOOK_URL не установлен")
            raise ValueError("WEBHOOK_URL не установлен")
        if not BOT_TOKEN:
            logging.error("BOT_TOKEN не установлен")
            raise ValueError("BOT_TOKEN не установлен")
        
        await ptb.bot.setWebhook(webhook_url)
        logging.info("Webhook установлен: %s", webhook_url)
        await ptb.initialize()
        await ptb.start()
        logging.info("Бот успешно запущен")

        # Запуск планировщика в фоновом режиме
        async def run_scheduler():
            logging.info("Запуск планировщика")
            while True:
                schedule.run_pending()
                await asyncio.sleep(1)
        
        ptb.create_task(run_scheduler())
    except Exception as e:
        logging.error("Ошибка при запуске бота: %s", e)
        raise

@app.on_event("shutdown")
async def on_shutdown():
    """Остановка бота"""
    logging.info("Остановка бота")
    await ptb.stop()

# Добавление обработчиков команд
ptb.add_handler(CommandHandler("start", start))
ptb.add_handler(CommandHandler("stop", stop))

if __name__ == "__main__":
    import uvicorn
    logging.info("Запуск Uvicorn")
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))