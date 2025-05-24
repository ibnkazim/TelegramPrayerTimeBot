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

BOT_TOKEN = "7402773153:AAFxzD6OGtPEdsH87l9v_sfv6_3nOlg3PD4"  
PRAYER_URL = "https://qmdi.ru/raspisanie-namazov/"
SUBSCRIBERS_FILE = "subscribers.json"

bot = telegram.Bot(token=BOT_TOKEN)
updater = Updater(BOT_TOKEN, use_context=True)

# Хранилище расписания намаза и подписчиков
prayer_times = {}
subscribers = set()

def load_subscribers():
    """Загрузка подписчиков из файла"""
    global subscribers
    if os.path.exists(SUBSCRIBERS_FILE):
        with open(SUBSCRIBERS_FILE, "r") as f:
            subscribers = set(json.load(f))
    return subscribers

def save_subscribers():
    """Сохранение подписчиков в файл"""
    with open(SUBSCRIBERS_FILE, "w") as f:
        json.dump(list(subscribers), f)



async def fetch_prayer_times():
    """Получение времени намаза с сайта qmdi.ru"""
    try:
        response = requests.get(PRAYER_URL)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        
        table = soup.find("table")
        if not table:
            print("Таблица не найдена")
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
                return True
        print(f"Расписание на {today} не найдено")
        return False
    except Exception as e:
        print(f"Ошибка при парсинге: {e}")
        return False

async def send_prayer_notification(prayer_name, prayer_time):
    """Отправка уведомления о намазе всем подписчикам"""
    message = f"Время намаза {prayer_name}: {prayer_time}"
    for chat_id in subscribers:
        try:
            await bot.send_message(chat_id=chat_id, text=message)
            print(f"Уведомление отправлено {chat_id}: {message}")
        except Exception as e:
            print(f"Ошибка при отправке {chat_id}: {e}")

def schedule_prayer_notifications():
    """Планирование уведомлений"""
    schedule.clear()
    for prayer, time_str in prayer_times.items():
        schedule.every().day.at(time_str).do(
            lambda p=prayer, t=time_str: asyncio.ensure_future(send_prayer_notification(p, t))
        )

async def update_prayer_times_daily():
    """Ежедневное обновление расписания"""
    if await fetch_prayer_times():
        schedule_prayer_notifications()
        print("Расписание намаза обновлено:", prayer_times)
    else:
        print("Не удалось обновить расписание")

async def start(update, context):
    """Обработка команды /start"""
    chat_id = update.message.chat.id
    if chat_id not in subscribers:
        subscribers.add(chat_id)
        save_subscribers()
        await update.message.reply_text("Вы подписались на уведомления о намазе!")
    else:
        await update.message.reply_text("Вы уже подписаны на уведомления.")

async def stop(update, context):
    """Обработка команды /stop"""
    chat_id = update.message.chat.id
    if chat_id in subscribers:
        subscribers.remove(chat_id)
        save_subscribers()
        await update.message.reply_text("Вы отписались от уведомлений.")
    else:
        await update.message.reply_text("Вы не подписаны на уведомления.")

def setup_handlers():
    """Настройка обработчиков команд"""
    dp = updater.dispatcher
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("stop", stop))
    updater.start_polling()

async def main():
    """Основная функция"""
    # Загружаем подписчиков
    load_subscribers()
    
    # Начальная загрузка расписания
    await update_prayer_times_daily()
    
    # Планируем ежедневное обновление в 00:01
    schedule.every().day.at("00:01").do(
        lambda: asyncio.ensure_future(update_prayer_times_daily())
    )
    
    # Запускаем обработчики команд
    setup_handlers()
    
    # Запускаем планировщик
    while True:
        schedule.run_pending()
        await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(main())