import asyncio
import requests
from bs4 import BeautifulSoup
import schedule
from datetime import datetime, timezone, timedelta
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from fastapi import FastAPI, Request, Response
from http import HTTPStatus
import json
import os
import logging
import sys
import random
import aiohttp

# Проверка наличия pytz
try:
    import pytz
 художественный PYTZ_AVAILABLE = True
except ImportError:
    PYTZ_AVAILABLE = False
    logging.warning("Модуль pytz не установлен, используется конверсия времени в UTC")

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
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
PRAYER_URL = "https://qmdi.ru/raspisanie-namazov/"
SUBSCRIBERS_FILE = "./subscribers.json"  # Явный путь в корне проекта

# Проверка переменных окружения
logging.info("Проверка переменных окружения: BOT_TOKEN=%s, WEBHOOK_URL=%s, PORT=%s",
             "set" if BOT_TOKEN else "not set", WEBHOOK_URL, os.getenv("PORT"))

# Инициализация FastAPI
app = FastAPI()

# Инициализация бота
ptb = Application.builder().token(BOT_TOKEN).updater(None).build()

# Хранилище расписания намаза и подписчиков
prayer_times = {}
subscribers = set()

# Список хадисов из Сахих аль-Бухари
HADITHS = [
    {
        "text": "Пророк (мир ему) сказал: 'Кто совершит намаз в два ракаата перед утренней молитвой, тот будет защищен от огня.'",
        "reference": "Книга 8, Хадис 468"
    },
    {
        "text": "Пророк (мир ему) сказал: 'Пять ежедневных молитв подобны реке, протекающей у ваших дверей, в которой вы омываетесь пять раз в день.'",
        "reference": "Книга 10, Хадис 528"
    },
    {
        "text": "Пророк (мир ему) сказал: 'Тот, кто пропустит молитву Аср, как будто потерял свою семью и имущество.'",
        "reference": "Книга 10, Хадис 527"
    },
    {
        "text": "Пророк (мир ему) сказал: 'Деяния оцениваются по намерениям, и каждому человеку достанется то, что он намеревался.'",
        "reference": "Книга 1, Хадис 1"
    },
    {
        "text": "Пророк (мир ему) сказал: 'Тому, кто прочитает трижды каждое утро и вечер: «С именем Аллаха, с которым ничто не вредит ни на земле, ни в небесах, и Он — Слышащий, Знающий», — ничто не повредит.'",
        "reference": "Книга 54, Хадис 419"
    }
]

# Определение клавиатуры
REPLY_KEYBOARD = ReplyKeyboardMarkup([
    [KeyboardButton("Подписаться на уведомления"), KeyboardButton("Отписаться")],
    [KeyboardButton("Расписание намазов"), KeyboardButton("Случайный хадис")],
    [KeyboardButton("Связаться с разработчиком")]
], resize_keyboard=True, one_time_keyboard=False)

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
            logging.info("Файл подписчиков не существует, создается новый")
            save_subscribers()  # Создаем пустой файл
    except Exception as e:
        logging.error("Ошибка загрузки подписчиков: %s", e)
    return subscribers

def save_subscribers():
    """Сохранение подписчиков в файл"""
    logging.info("Сохранение подписчиков в %s", SUBSCRIBERS_FILE)
    try:
        with open(SUBSCRIBERS_FILE, "w") as f:
            json.dump(list(subscribers), f)
        logging.info("Подписчики сохранены: %s", subscribers)
    except Exception as e:
        logging.error("Ошибка сохранения подписчиков: %s", e)

async def fetch_prayer_times():
    """Получение времени намаза с сайта qmdi.ru"""
    logging.info("Начало парсинга расписания с %s", PRAYER_URL)
    try:
        response = requests.get(PRAYER_URL, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        
        table = soup.find("table")
        if not table:
            logging.error("Таблица не найдена")
            return False
        
        rows = table.find_all("tr")[1:]
        today = datetime.now(timezone(timedelta(hours=3)))  # MSK
        date_formats = [
            today.strftime("%d.%m.%Y"),  # 24.05.2025
            today.strftime("%d.%m.%y"),  # 24.05.25
            today.strftime("%d %B %Y").lower(),  # 24 мая 2025
            today.strftime("%d.%m")  # 24.05
        ]
        logging.info("Проверяемые форматы даты: %s", date_formats)
        
        for row in rows:
            cells = row.find_all("td")
            if len(cells) >= 6:
                date_text = cells[0].text.strip().lower()
                logging.info("Найдена дата в таблице: %s", date_text)
                if any(date_format in date_text for date_format in date_formats):
                    prayer_times.update({
                        "Фаджр": cells[1].text.strip(),
                        "Зухр": cells[2].text.strip(),
                        "Аср": cells[3].text.strip(),
                        "Магриб": cells[4].text.strip(),
                        "Иша": cells[5].text.strip()
                    })
                    logging.info("Расписание найдено: %s", prayer_times)
                    return True
        logging.warning("Расписание на %s не найдено", date_formats)
        return False
    except Exception as e:
        logging.error("Ошибка парсинга: %s", e)
        return False

async def send_prayer_notification(prayer_name: str, prayer_time: str):
    """Отправка уведомления о намазе всем подписчикам"""
    logging.info("Вызов send_prayer_notification: %s на %s", prayer_name, prayer_time)
    now_msk = datetime.now(timezone(timedelta(hours=3))).strftime("%H:%M:%S")  # MSK
    now_utc = datetime.now(timezone.utc).strftime("%H:%M:%S")  # UTC
    message = f"Спешите на намаз! Спешите к спасению! {prayer_name}: {prayer_time} (MSK: {now_msk}, UTC: {now_utc})"
    logging.info("Отправка уведомления: %s, подписчики: %s", message, subscribers)
    try:
        for chat_id in subscribers:
            try:
                await ptb.bot.send_message(chat_id=chat_id, text=message)
                logging.info("Уведомление отправлено %s: %s", chat_id, message)
            except Exception as e:
                logging.error("Ошибка при отправке %s: %s", chat_id, e)
    except Exception as e:
        logging.error("Общая ошибка в send_prayer_notification: %s", e)

def schedule_prayer_notifications():
    """Планирование уведомлений"""
    schedule.clear()
    logging.info("Планирование уведомлений")
    msk_tz = timezone(timedelta(hours=3))
    for prayer, time_str in prayer_times.items():
        try:
            # Конвертируем MSK время в UTC для сервера
            msk_time = datetime.strptime(time_str, "%H:%M").replace(
                tzinfo=msk_tz, year=2025, month=5, day=24
            )
            utc_time = msk_time.astimezone(timezone.utc).strftime("%H:%M")
            schedule.every().day.at(utc_time).do(
                lambda p=prayer, t=time_str: ptb.create_task(send_prayer_notification(p, t))
            )
            logging.info("Запланировано: %s на %s MSK (%s UTC)", prayer, time_str, utc_time)
        except ValueError as e:
            logging.error("Ошибка формата времени для %s: %s", prayer, e)
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
        await update.message.reply_text(
            "Ас-саляму алейкум уа рахматуллахи уа баракатуху! Вы подписались на уведомления о намазе!",
            reply_markup=REPLY_KEYBOARD
        )
        logging.info("Новый подписчик: %s", chat_id)
    else:
        await update.message.reply_text(
            "Вы уже подписаны на уведомления.",
            reply_markup=REPLY_KEYBOARD
        )
        logging.info("Повторная подписка: %s", chat_id)

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка команды /stop"""
    chat_id = update.effective_chat.id
    logging.info("Команда /stop от %s", chat_id)
    if chat_id in subscribers:
        subscribers.remove(chat_id)
        save_subscribers()
        await update.message.reply_text(
            "Вы отписались от уведомлений.",
            reply_markup=REPLY_KEYBOARD
        )
        logging.info("Подписчик отписался: %s", chat_id)
    else:
        await update.message.reply_text(
            "Вы не подписаны на уведомления.",
            reply_markup=REPLY_KEYBOARD
        )
        logging.info("Попытка отписки неподписанного: %s", chat_id)

async def show_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка команды /schedule для отображения расписания намазов"""
    chat_id = update.effective_chat.id
    logging.info("Команда /schedule от %s", chat_id)
    if prayer_times:
        schedule_text = "Расписание намазов на сегодня:\n"
        for prayer, time in prayer_times.items():
            schedule_text += f"{prayer}: {time}\n"
        await update.message.reply_text(schedule_text, reply_markup=REPLY_KEYBOARD)
        logging.info("Расписание отправлено %s: %s", chat_id, schedule_text)
    else:
        await update.message.reply_text(
            "Расписание на сегодня недоступно.",
            reply_markup=REPLY_KEYBOARD
        )
        logging.info("Расписание недоступно для %s", chat_id)

async def show_hadith(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка команды /hadith для отображения случайного хадиса"""
    chat_id = update.effective_chat.id
    logging.info("Команда /hadith от %s", chat_id)
    hadith = random.choice(HADITHS)
    message = f"Хадис из Сахих аль-Бухари:\n{hadith['text']} ({hadith['reference']})"
    await update.message.reply_text(message, reply_markup=REPLY_KEYBOARD)
    logging.info("Хадис отправлен %s: %s", chat_id, message)

async def contact_developer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка команды /contact для связи с разработчиком"""
    chat_id = update.effective_chat.id
    logging.info("Команда /contact от %s", chat_id)
    message = "Свяжитесь с разработчиком: @ibn_kazim"
    await update.message.reply_text(message, reply_markup=REPLY_KEYBOARD)
    logging.info("Контакт отправлен %s: %s", chat_id, message)

async def show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка команды /menu для отображения меню"""
    chat_id = update.effective_chat.id
    logging.info("Команда /menu от %s", chat_id)
    await update.message.reply_text(
        "Ас-саляму ‘аляйкум уа рахмату-Ллахи уа баракяту",
        reply_markup=REPLY_KEYBOARD
    )
    logging.info("Меню отправлено %s", chat_id)

async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка нажатий на кнопки"""
    chat_id = update.effective_chat.id
    text = update.message.text
    logging.info("Получен текст кнопки от %s: %s", chat_id, text)
    
    if text == "Подписаться на уведомления":
        await start(update, context)
    elif text == "Отписаться":
        await stop(update, context)
    elif text == "Расписание намазов":
        await show_schedule(update, context)
    elif text == "Случайный хадис":
        await show_hadith(update, context)
    elif text == "Связаться с разработчиком":
        await contact_developer(update, context)
    else:
        await update.message.reply_text(
            "Пожалуйста, используйте кнопки меню.",
            reply_markup=REPLY_KEYBOARD
        )
        logging.info("Неизвестный текст от %s: %s", chat_id, text)

async def keep_alive():
    """Фоновая задача для предотвращения засыпания сервера"""
    logging.info("Запуск keep_alive для предотвращения засыпания")
    async with aiohttp.ClientSession() as session:
        while True:
            try:
                async with session.get(WEBHOOK_URL) as response:
                    if response.status == 200:
                        logging.info("Успешный пинг сервера: %s", WEBHOOK_URL)
                    else:
                        logging.error("Ошибка пинга сервера: статус %s", response.status)
                await asyncio.sleep(14 * 60)  # Пинг каждые 14 минут
            except Exception as e:
                logging.error("Ошибка в keep_alive: %s", e)
                await asyncio.sleep(60)  # Ждём 1 минуту перед повтором

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

@app.get("/time")
async def get_time():
    """Отладка: текущее время сервера"""
    logging.info("Запрос текущего времени")
    return {
        "msk_time": datetime.now(timezone(timedelta(hours=3))).strftime("%H:%M:%S"),
        "utc_time": datetime.now(timezone.utc).strftime("%H:%M:%S")
    }

# FastAPI lifespan для настройки webhook
@app.on_event("startup")
async def on_startup():
    """Настройка webhook и запуск бота"""
    logging.info("Запуск бота")
    try:
        load_subscribers()
        if not await fetch_prayer_times():
            logging.warning("Используется тестовое расписание")
            now = datetime.now(timezone(timedelta(hours=3)))  # MSK
            future = now + timedelta(minutes=2)  # Уведомление через 2 минуты
            prayer_times.update({
                "Фаджр": future.strftime("%H:%M"),  # Быстрый тест
                "Зухр": "12:00",
                "Аср": "16:00",
                "Магриб": "18:30",
                "Иша": "20:00"
            })
            logging.info("Тестовое расписание: %s", prayer_times)
        schedule_prayer_notifications()
        schedule.every().day.at("00:01").do(
            lambda: ptb.create_task(update_prayer_times_daily())
        )
        if not WEBHOOK_URL:
            logging.error("WEBHOOK_URL не установлен")
            raise ValueError("WEBHOOK_URL не установлен")
        if not BOT_TOKEN:
            logging.error("BOT_TOKEN не установлен")
            raise ValueError("BOT_TOKEN не установлен")
        
        await ptb.bot.setWebhook(WEBHOOK_URL)
        logging.info("Webhook установлен: %s", WEBHOOK_URL)
        await ptb.initialize()
        await ptb.start()
        logging.info("Бот успешно запущен")

        async def run_scheduler():
            logging.info("Запуск планировщика")
            while True:
                try:
                    now_msk = datetime.now(timezone(timedelta(hours=3))).strftime("%H:%M:%S")
                    now_utc = datetime.now(timezone.utc).strftime("%H:%M:%S")
                    logging.debug("Планировщик активен: MSK=%s, UTC=%s", now_msk, now_utc)
                    schedule.run_pending()
                    await asyncio.sleep(1)
                except Exception as e:
                    logging.error("Ошибка в планировщике: %s", e)
                    await asyncio.sleep(5)
        
        ptb.create_task(run_scheduler())
        ptb.create_task(keep_alive())  # Запуск keep_alive
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
ptb.add_handler(CommandHandler("schedule", show_schedule))
ptb.add_handler(CommandHandler("hadith", show_hadith))
ptb.add_handler(CommandHandler("contact", contact_developer))
ptb.add_handler(CommandHandler("menu", show_menu))
ptb.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_buttons))

if __name__ == "__main__":
    import uvicorn
    logging.info("Запуск Uvicorn")
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))