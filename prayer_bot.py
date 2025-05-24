import asyncio
import requests
from bs4 import BeautifulSoup
import schedule
import time
from datetime import datetime
import telegram
from telegram.ext import Updater, CommandHandler
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
bot = telegram.Bot(token=BOT_TOKEN)
updater = Updater(BOT_TOKEN, use_context=True)

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
            logging.error("Ошибка при загрузке подписчиков: %s", e)
    return subscribers

def save_subscribers():
    """Сохранение подписчиков в файл"""
    try:
        with open(SUBSCRIBERS_FILE, "w") as f:
            json.dump(list(subscribers), f)
        logging.info("Подписчики сохранены: %s", subscribers)
    except Exception as e:
        logging.error("Ошибка при сохранении подписчиков: %s", e)


async def fetch_prayer_times():
    # Для теста
    prayer_times.update({
        "Фаджр": (datetime.now().strftime("%H:%M")),  # Текущее время
        "Зухр": "12:00",
        "Аср": "16:00",
        "Магриб": "18:30",
        "Иша": "20:00"
    })
    return True


# async def fetch_prayer_times():
#     """Получение времени намаза с сайта qmdi.ru"""
#     try:
#         response = requests.get(PRAYER_URL)
#         response.raise_for_status()
#         soup = BeautifulSoup(response.text, "html.parser")
        
#         table = soup.find("table")
#         if not table:
#             logging.error("Таблица не найдена")
#             return False
        
#         rows = table.find_all("tr")[1:]
#         today = datetime.now().strftime("%d.%m.%Y")
        
#         for row in rows:
#             cells = row.find_all("td")
#             if len(cells) >= 6 and cells[0].text.strip() == today:
#                 prayer_times.update({
#                     "Фаджр(Сабах)": cells[1].text.strip(),
#                     "Зухр(Уйле)": cells[2].text.strip(),
#                     "Аср(Экнди)": cells[3].text.strip(),
#                     "Магриб(Акъшам)": cells[4].text.strip(),
#                     "Иша(Ятсы)": cells[5].text.strip()
#                 })
#                 logging.info("Расписание намаза обновлено: %s", prayer_times)
#                 return True
#         logging.warning("Расписание на %s не найдено", today)
#         return False
#     except Exception as e:
#         logging.error("Ошибка при парсинге: %s", e)
#         return False

async def send_prayer_notification(prayer_name, prayer_time):
    """Отправка уведомления о намазе всем подписчикам"""
    message = f"Время намаза {prayer_name}: {prayer_time}"
    for chat_id in subscribers:
        try:
            await bot.send_message(chat_id=chat_id, text=message)
            logging.info("Уведомление отправлено %s: %s", chat_id, message)
        except Exception as e:
            logging.error("Ошибка при отправке %s: %s", chat_id, e)

def schedule_prayer_notifications():
    """Планирование уведомлений"""
    schedule.clear()
    for prayer, time_str in prayer_times.items():
        schedule.every().day.at(time_str).do(
            lambda p=prayer, t=time_str: asyncio.ensure_future(send_prayer_notification(p, t))
        )
    logging.info("Уведомления запланированы: %s", prayer_times)

async def update_prayer_times_daily():
    """Ежедневное обновление расписания"""
    if await fetch_prayer_times():
        schedule_prayer_notifications()
    else:
        logging.error("Не удалось обновить расписание")

async def start(update, context):
    """Обработка команды /start"""
    chat_id = update.message.chat.id
    if chat_id not in subscribers:
        subscribers.add(chat_id)
        save_subscribers()
        await update.message.reply_text("Вы подписались на уведомления о намазе!")
        logging.info("Новый подписчик: %s", chat_id)
    else:
        await update.message.reply_text("Вы уже подписаны на уведомления.")
        logging.info("Повторная подписка: %s", chat_id)

async def stop(update, context):
    """Обработка команды /stop"""
    chat_id = update.message.chat.id
    if chat_id in subscribers:
        subscribers.remove(chat_id)
        save_subscribers()
        await update.message.reply_text("Вы отписались от уведомлений.")
        logging.info("Подписчик отписался: %s", chat_id)
    else:
        await update.message.reply_text("Вы не подписаны на уведомления.")
        logging.info("Попытка отписки неподписанного: %s", chat_id)

def setup_handlers():
    """Настройка обработчиков команд"""
    dp = updater.dispatcher
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("stop", stop))
    updater.start_polling()
    logging.info("Обработчики команд настроены")

async def main():
    """Основная функция"""
    logging.info("Бот запущен")
    load_subscribers()
    await update_prayer_times_daily()
    schedule.every().day.at("00:01").do(
        lambda: asyncio.ensure_future(update_prayer_times_daily())
    )
    setup_handlers()
    while True:
        schedule.run_pending()
        await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(main())