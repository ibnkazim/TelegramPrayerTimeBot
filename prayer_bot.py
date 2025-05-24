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