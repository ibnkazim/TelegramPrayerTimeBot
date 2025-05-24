import asyncio
import requests
from bs4 import BeautifulSoup
import schedule
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import json
import os
import logging

# Настройка логирования
logging.basicConfig(filename='prayer_bot.log', level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

# Конфигурация
BOT_TOKEN = "7402773153:AAFxzD6OGtPEdsH87l9v_sfv6_3nOlg3PD4"  
PRAYER_URL = "https://qmdi.ru/raspisanie-namazov/"
SUBSCRIBERS_FILE = "subscribers.json"

# Инициализация бота
app = Application.builder().token(BOT_TOKEN).build()

# Хранилище расписания намаза и подписчиков
prayer_times = {}
subscribers = set()

def load_subscribers():
    """Загрузка подписчиков из файла"""
    global subscribers
    if os.path.exists(SUBSCRIBERS_FILE):
        try:
            with open(SUBSCRIBERS_FILE, "r") as f:
                subscribers = set(json.load(f))
            logging.info("Подписчики загружены: %s", subscribers)
        except Exception as e:
            logging.error("Ошибка загрузки подписчиков: %s", e)
    return subscribers

def save_subscribers():
    """Сохранение подписчиков в файл"""
    try:
        with open(SUBSCRIBERS_FILE, "w") as f:
            json.dump(list(subscribers), f)
        logging.info("Подписчики сохранены: %s", subscribers)
    except Exception as e:
        logging.error("Ошибка сохранения подписчиков: %s", e)

async def fetch_prayer_times():
    """Получение времени намаза с сайта qmdi.ru"""
    try:
        response = requests.get(PRAYER_URL)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        
        table = soup.find("table")
        if not table:
            logging.error("Таблица не найдена")
            return False
        
        rows = table.find_all("tr")[1:]
        today = datetime.now().strftime("%d.%m.%Y")
        
        for row in rows:
            cells = row.find_all("td")
            if len(cells) >= 6 and cells[0].text.strip() == today:
                prayer_times.update({
                    "Фаджр(Сабах)": cells[1].text.strip(),
                    "Зухр(Уйле)": cells[2].text.strip(),
                    "Аср(Экинди)": cells[3].text.strip(),
                    "Магриб(Акъшам)": cells[4].text.strip(),
                    "Иша(Ятсы)": cells[5].text.strip()
                })
                logging.info("Расписание намаза обновлено: %s", prayer_times)
                return True
        logging.warning("Расписание на %s не найдено", today)
        return False
    except Exception as e:
        logging.error("Ошибка при парсинге: %s", e)
        return False

async def send_prayer_notification(context: ContextTypes.DEFAULT_TYPE, prayer_name: str, prayer_time: str):
    """Отправка уведомления о намазе всем подписчикам"""
    message = f"Время намаза {prayer_name}: {prayer_time}"
    for chat_id in subscribers:
        try:
            await context.bot.send_message(chat_id=chat_id, text=message)
            logging.info("Уведомление отправлено %s: %s", chat_id, message)
        except Exception as e:
            logging.error("Ошибка при отправке %s: %s", chat_id, e)

def schedule_prayer_notifications():
    """Планирование уведомлений"""
    schedule.clear()
    for prayer, time_str in prayer_times.items():
        schedule.every().day.at(time_str).do(
            lambda p=prayer, t=time_str: app.create_task(send_prayer_notification(app, p, t))
        )
    logging.info("Уведомления запланированы: %s", prayer_times)

async def update_prayer_times_daily():
    """Ежедневное обновление расписания"""
    if await fetch_prayer_times():
        schedule_prayer_notifications()
    else:
        logging.error("Не удалось обновить расписание")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка команды /start"""
    chat_id = update.effective_chat.id
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
    if chat_id in subscribers:
        subscribers.remove(chat_id)
        save_subscribers()
        await update.message.reply_text("Вы отписались от уведомлений.")
        logging.info("Подписчик отписался: %s", chat_id)
    else:
        await update.message.reply_text("Вы не подписаны на уведомления.")
        logging.info("Попытка отписки неподписанного: %s", chat_id)

async def main():
    """Основная функция"""
    logging.info("Бот запущен")
    load_subscribers()
    await update_prayer_times_daily()
    schedule.every().day.at("00:01").do(
        lambda: app.create_task(update_prayer_times_daily())
    )
    
    # Добавление обработчиков команд
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stop", stop))
    
    # Запуск бота
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    
    # Запуск планировщика
    while True:
        schedule.run_pending()
        await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(main())