mport asyncio
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
