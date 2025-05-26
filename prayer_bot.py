```python
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
    PYTZ_AVAILABLE = True
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

# Хранилище расписания намаза, исламской даты и подписчиков
prayer_times = {}
islamic_date = {"day": "", "month": "", "year": ""}
subscribers = set()

# Список хадисов из Сахих аль-Бухари и Сахих Муслима (на русском)
HADITHS = [
    {
        "text": "Пророк (мир ему) сказал: 'Кто совершит намаз в два ракаата перед утренней молитвой, тот будет защищен от огня.'",
        "reference": "Sahih al-Bukhari, Книга 8, Хадис 468"
    },
    {
        "text": "Пророк (мир ему) сказал: 'Пять ежедневных молитв подобны реке, протекающей у ваших дверей, в которой вы омываетесь пять раз в день.'",
        "reference": "Sahih al-Bukhari, Книга 10, Хадис 528"
    },
    {
        "text": "Пророк (мир ему) сказал: 'Тот, кто пропустит молитву Аср, как будто потерял свою семью и имущество.'",
        "reference": "Sahih al-Bukhari, Книга 10, Хадис 527"
    },
    {
        "text": "Пророк (мир ему) сказал: 'Деяния оцениваются по намерениям, и каждому человеку достанется то, что он намеревался.'",
        "reference": "Sahih al-Bukhari, Книга 1, Хадис 1"
    },
    {
        "text": "Пророк (мир ему) сказал: 'Тому, кто прочитает трижды каждое утро и вечер: «С именем Аллаха, с которым ничто не вредит ни на земле, ни в небесах, и Он — Слышащий, Знающий», — ничто не повредит.'",
        "reference": "Sahih al-Bukhari, Книга 54, Хадис 419"
    },
    {
        "text": "Пророк (мир ему) сказал: 'Молитва в моей мечети лучше тысячи молитв в других мечетях, кроме Заповедной мечети.'",
        "reference": "Sahih al-Bukhari, Книга 25, Хадис 1190"
    },
    {
        "text": "Пророк (мир ему) сказал: 'Кто очищается в своем доме, затем идет в мечеть, тот получит награду за каждый шаг.'",
        "reference": "Sahih Muslim, Книга 5, Хадис 666"
    },
    {
        "text": "Пророк (мир ему) сказал: 'Молитва в собрании в двадцать семь раз превосходит молитву, совершенную в одиночестве.'",
        "reference": "Sahih al-Bukhari, Книга 11, Хадис 645"
    },
    {
        "text": "Пророк (мир ему) сказал: 'Самое трудное для лицемеров — это молитвы Иша и Фаджр.'",
        "reference": "Sahih al-Bukhari, Книга 11, Хадис 657"
    },
    {
        "text": "Пророк (мир ему) сказал: 'Кто пропустит молитву умышленно, тот лишается защиты Аллаха.'",
        "reference": "Sahih Muslim, Книга 4, Хадис 670"
    },
    {
        "text": "Пророк (мир ему) сказал: 'Первое, о чем спросят раба в Судный день, — это его молитва.'",
        "reference": "Sahih Muslim, Книга 4, Хадис 1398"
    },
    {
        "text": "Пророк (мир ему) сказал: 'Молитва — это свет, милостыня — доказательство, а терпение — сияние.'",
        "reference": "Sahih Muslim, Книга 1, Хадис 223"
    },
    {
        "text": "Пророк (мир ему) сказал: 'Кто совершает омовение должным образом, тому прощаются его прежние грехи.'",
        "reference": "Sahih al-Bukhari, Книга 4, Хадис 192"
    },
    {
        "text": "Пророк (мир ему) сказал: 'Кто читает аят аль-Курси после каждой обязательной молитвы, тот будет защищен до следующей молитвы.'",
        "reference": "Sahih Muslim, Книга 4, Хадис 807"
    },
    {
        "text": "Пророк (мир ему) сказал: 'Два ракаата Фаджр лучше всего мира и того, что в нем.'",
        "reference": "Sahih Muslim, Книга 4, Хадис 1573"
    },
    {
        "text": "Пророк (мир ему) сказал: 'Кто молится перед восходом и перед закатом, тот не войдет в Огонь.'",
        "reference": "Sahih Muslim, Книга 4, Хадис 635"
    },
    {
        "text": "Пророк (мир ему) сказал: 'Между человеком и неверием — оставление молитвы.'",
        "reference": "Sahih Muslim, Книга 1, Хадис 82"
    },
    {
        "text": "Пророк (мир ему) сказал: 'Ключ к Раю — это молитва, а ключ к молитве — омовение.'",
        "reference": "Sahih Muslim, Книга 4, Хадис 4"
    },
    {
        "text": "Пророк (мир ему) сказал: 'Кто совершает молитву ради Аллаха сорок дней в собрании, тому записывается защита от лицемерия.'",
        "reference": "Sahih Muslim, Книга 4, Хадис 141"
    },
    {
        "text": "Пророк (мир ему) сказал: 'Лучшее дело — это молитва в свое время.'",
        "reference": "Sahih al-Bukhari, Книга 10, Хадис 579"
    },
    {
        "text": "Пророк (мир ему) сказал: 'Кто оставит молитву, тот встретит Аллаха в гневе.'",
        "reference": "Sahih al-Bukhari, Книга 10, Хадис 580"
    },
    {
        "text": "Пророк (мир ему) сказал: 'Молитва — это связь между рабом и его Господом.'",
        "reference": "Sahih Muslim, Книга 4, Хадис 146"
    },
    {
        "text": "Пророк (мир ему) сказал: 'Кто молится ночью, тому Аллах придает свет в лицо.'",
        "reference": "Sahih Muslim, Книга 6, Хадис 1169"
    },
    {
        "text": "Пророк (мир ему) сказал: 'Самое любимое дело у Аллаха — это молитва в ее время.'",
        "reference": "Sahih al-Bukhari, Книга 10, Хадис 597"
    },
    {
        "text": "Пророк (мир ему) сказал: 'Кто совершает молитву Зухр в жару, тот получает награду, подобную освобождению раба.'",
        "reference": "Sahih al-Bukhari, Книга 11, Хадис 629"
    },
    {
        "text": "Пророк (мир ему) сказал: 'Молитва Магриб — это свидетельство веры.'",
        "reference": "Sahih Muslim, Книга 4, Хадис 625"
    },
    {
        "text": "Пророк (мир ему) сказал: 'Кто совершает молитву Иша в собрании, тот как будто молился половину ночи.'",
        "reference": "Sahih Muslim, Книга 4, Хадис 656"
    },
    {
        "text": "Пророк (мир ему) сказал: 'Молитва в трудное время — это лучшее из дел.'",
        "reference": "Sahih al-Bukhari, Книга 11, Хадис 634"
    },
    {
        "text": "Пророк (мир ему) сказал: 'Кто забыл молитву, пусть совершит ее, когда вспомнит.'",
        "reference": "Sahih al-Bukhari, Книга 10, Хадис 597"
    },
    {
        "text": "Пророк (мир ему) сказал: 'Молитва — это милость Аллаха для верующих.'",
        "reference": "Sahih Muslim, Книга 4, Хадис 654"
    },
    {
        "text": "Пророк (мир ему) сказал: 'Кто молится двенадцать ракаатов в день и ночь добровольно, тому будет построен дом в Раю.'",
        "reference": "Sahih Muslim, Книга 4, Хадис 785"
    },
    {
        "text": "Пророк (мир ему) сказал: 'Молитва в Заповедной мечети в сто тысяч раз лучше, чем в других.'",
        "reference": "Sahih al-Bukhari, Книга 25, Хадис 1189"
    },
    {
        "text": "Пророк (мир ему) сказал: 'Кто совершает молитву с искренностью, тот обретает покой в сердце.'",
        "reference": "Sahih Muslim, Книга 4, Хадис 661"
    },
    {
        "text": "Пророк (мир ему) сказал: 'Молитва — это первое, что будет взвешено в Судный день.'",
        "reference": "Sahih al-Bukhari, Книга 10, Хадис 630"
    },
    {
        "text": "Пророк (мир ему) сказал: 'Кто молится Фаджр в собрании, тот находится под защитой Аллаха.'",
        "reference": "Sahih Muslim, Книга 4, Хадис 657"
    },
    {
        "text": "Пророк (мир ему) сказал: 'Вера — это убежденность в сердце, подтверждение языком и дела руками.'",
        "reference": "Sahih Muslim, Книга 1, Хадис 8"
    },
    {
        "text": "Пророк (мир ему) сказал: 'Кто скажет: «Нет божества, кроме Аллаха», искренне, тот войдет в Рай.'",
        "reference": "Sahih al-Bukhari, Книга 93, Хадис 6480"
    },
    {
        "text": "Пророк (мир ему) сказал: 'В Судный день люди будут воскрешены босыми, нагими и необрезанными.'",
        "reference": "Sahih al-Bukhari, Книга 60, Хадис 3349"
    },
    {
        "text": "Пророк (мир ему) сказал: 'Среди признаков Часа — распространение невежества и уменьшение знаний.'",
        "reference": "Sahih al-Bukhari, Книга 3, Хадис 80"
    },
    {
        "text": "Пророк (мир ему) сказал: 'Вера состоит из более чем семидесяти ветвей, высшая из которых — свидетельство, что нет божества, кроме Аллаха.'",
        "reference": "Sahih Muslim, Книга 1, Хадис 35"
    },
    {
        "text": "Пророк (мир ему) сказал: 'В Судный день солнце приблизится к людям, и они будут тонуть в своем поту.'",
        "reference": "Sahih Muslim, Книга 40, Хадис 2944"
    },
    {
        "text": "Пророк (мир ему) сказал: 'Кто умрет, веря в Аллаха и Последний день, тот войдет в Рай.'",
        "reference": "Sahih al-Bukhari, Книга 23, Хадис 1360"
    },
    {
        "text": "Пророк (мир ему) сказал: 'В Судный день каждый будет призван по имени своей матери, чтобы скрыть его позор.'",
        "reference": "Sahih Muslim, Книга 40, Хадис 2951"
    },
    {
        "text": "Пророк (мир ему) сказал: 'Иман — это вера в Аллаха, Его ангелов, Его книги, Его посланников, Последний день и предопределение.'",
        "reference": "Sahih Muslim, Книга 1, Хадис 1"
    },
    {
        "text": "Пророк (мир ему) сказал: 'В Судный день мост Сират будет тоньше волоса и острее меча.'",
        "reference": "Sahih Muslim, Книга 1, Хадис 183"
    },
    {
        "text": "Пророк (мир ему) сказал: 'Кто любит ради Аллаха и ненавидит ради Аллаха, тот совершенствует свою веру.'",
        "reference": "Sahih al-Bukhari, Книга 2, Хадис 15"
    },
    {
        "text": "Пророк (мир ему) сказал: 'В Судный день праведники будут сиять светом своих деяний.'",
        "reference": "Sahih al-Bukhari, Книга 60, Хадис 3359"
    }
]

# Список утренних и вечерних азкаров (на русском)
ADHKAR = [
    {
        "text": "С именем Аллаха, с которым ничто не вредит ни на земле, ни в небесах, и Он — Слышащий, Знающий. (Бисмилляхи ллязи ля ядурру ма‘а исмихи шай’ун филь-арди ва ля фис-сама’и ва хувас-сами‘уль-‘алим)",
        "repetition": "3 раза",
        "source": "Hisn al-Muslim, №24"
    },
    {
        "text": "Я доволен Аллахом как Господом, Исламом как религией и Мухаммадом как пророком. (Радиту билляхи Раббан, ва биль-Ислами динан, ва би Мухаммадин набиййан)",
        "repetition": "3 раза",
        "source": "Hisn al-Muslim, №26"
    },
    {
        "text": "О Аллах, защити меня от огня и введи меня в Рай. (Аллахумма аджarni минан-нари ва адхильниль-джанна)",
        "repetition": "1 раз",
        "source": "Hisn al-Muslim, №78"
    },
    {
        "text": "Господь мой, я прошу у Тебя блага этого дня и блага после него. (Рабби, ас’алюка хайра хаза ль-йауми ва хайра ма ба‘даху)",
        "repetition": "1 раз (утром)",
        "source": "Hisn al-Muslim, №71"
    },
    {
        "text": "О Аллах, Ты мой Господь, нет божества, кроме Тебя, я полагаюсь на Тебя. (Аллахумма Анта Рабби, ля иляха илля Анта, ‘аляйка таваккяльту)",
        "repetition": "1 раз",
        "source": "Hisn al-Muslim, №65"
    },
    {
        "text": "Субханаллах (Слава Аллаху), Альхамдулиллях (Хвала Аллаху), Аллаху Акбар (Аллах Велик).",
        "repetition": "33 раза каждое",
        "source": "Hisn al-Muslim, №104"
    },
    {
        "text": "О Аллах, я ищу защиты у Тебя от шайтана и его козней. (Аллахумма инни а‘узу бика мин аш-шайтани ва хамазаатихи)",
        "repetition": "1 раз",
        "source": "Hisn al-Muslim, №55"
    },
    {
        "text": "Читает аят аль-Курси: Аллах — нет божества, кроме Него, Живого, Вечносущего... (Сура 2:255)",
        "repetition": "1 раз",
        "source": "Hisn al-Muslim, №12"
    }
]

# Определение клавиатуры
REPLY_KEYBOARD = ReplyKeyboardMarkup([
    [KeyboardButton("Подписаться на уведомления"), KeyboardButton("Отписаться")],
    [KeyboardButton("Расписание намазов"), KeyboardButton("Случайный хадис")],
    [KeyboardButton("Связаться с разработчиком"), KeyboardButton("Азкары")],
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
    """Получение времени намаза, восхода солнца и исламской даты с сайта qmdi.ru из блока <div class='date-namaz-main'>"""
    logging.info("Начало парсинга расписания, времени восхода и исламской даты с %s", PRAYER_URL)
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(PRAYER_URL, timeout=10) as response:
                response.raise_for_status()
                soup = BeautifulSoup(await response.text(), "html.parser")

                # Поиск блока с классом 'date-namaz-main'
                namaz_block = soup.find("div", class_="date-namaz-main")
                if not namaz_block:
                    logging.error("Блок 'date-namaz-main' не найден")
                    return False

                # Парсинг исламской даты
                islamic_calendar = namaz_block.find("div", class_="islCalendar")
                if islamic_calendar:
                    day = islamic_calendar.find("div", class_="islDate")
                    month = islamic_calendar.find("div", class_="islMonth")
                    year = islamic_calendar.find("div", class_="islYear")
                    if day and month and year:
                        islamic_date["day"] = day.text.strip()
                        islamic_date["month"] = month.text.strip()
                        islamic_date["year"] = year.text.strip().split(" | ")[0]
                        logging.info("Исламская дата найдена: %s", islamic_date)
                    else:
                        logging.warning("Не удалось извлечь исламскую дату")
                        islamic_date.update({"day": "", "month": "", "year": ""})
                else:
                    logging.warning("Блок 'islCalendar' не найден")
                    islamic_date.update({"day": "", "month": "", "year": ""})

                # Поиск таблицы с расписанием намазов
                table = namaz_block.find("table")
                if not table:
                    logging.error("Таблица не найдена в блоке 'date-namaz-main'")
                    return False

                # Словарь для сопоставления сокращённых названий с полными
                prayer_mapping = {
                    "Утр.": "Фаджр(Сабах)",
                    "Восх.": "Восход(Догъуш)",
                    "Обед.": "Зухр(Уйле)",
                    "Пол.": "Аср(Экинди)",
                    "Веч.": "Магриб(Акъшам)",
                    "Ноч.": "Иша(Ятсы)"
                }

                # Очистка текущего расписания
                prayer_times.clear()

                # Извлечение строк таблицы
                rows = table.find_all("tr")
                for row in rows:
                    cells = row.find_all("td")
                    if len(cells) >= 2:
                        prayer_short = cells[0].text.strip()  # Название намаза
                        prayer_time = cells[1].text.strip()   # Время намаза
                        if prayer_short in prayer_mapping:
                            prayer_times[prayer_mapping[prayer_short]] = prayer_time
                        else:
                            logging.debug("Пропущена строка с названием: %s", prayer_short)

                if prayer_times:
                    logging.info("Расписание найдено: %s", prayer_times)
                    return True
                else:
                    logging.warning("Расписание не найдено в таблице")
                    return False

    except Exception as e:
        logging.error("Ошибка парсинга: %s", e)
        return False

async def send_prayer_notification(prayer_name: str, prayer_time: str):
    """Отправка уведомления о намазе всем подписчикам"""
    logging.info("Вызов send_prayer_notification: %s на %s", prayer_name, prayer_time)
    now_msk = datetime.now(timezone(timedelta(hours=3))).strftime("%H:%M:%S")  # MSK
    now_utc = datetime.now(timezone.utc).strftime("%H:%M:%S")  # UTC
    if prayer_name == "Фаджр(Сабах)":
        message = f"{prayer_name}: {prayer_time} | Молитва лучше чем сон! Молитва лучше чем сон! (MSK: {now_msk}, UTC: {now_utc})"
    else:
        message = f"{prayer_name}: {prayer_time} | Спешите на намаз! Спешите к спасению! (MSK: {now_msk}, UTC: {now_utc})"
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
                tzinfo=msk_tz, year=2025, month=5, day=26
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
            "ДжазакАллаху хайран! Вы подписались на уведомления о намазе!",
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
    """Обработка команды /schedule для отображения расписания намазов, восхода и исламской даты"""
    chat_id = update.effective_chat.id
    logging.info("Команда /schedule от %s", chat_id)
    
    # Формирование текста исламской даты
    if islamic_date["day"] and islamic_date["month"] and islamic_date["year"]:
        hijri_text = f"Исламская дата: {islamic_date['day']} {islamic_date['month']} {islamic_date['year']} Хиджры"
    else:
        hijri_text = "Исламская дата недоступна"
    
    if prayer_times:
        schedule_text = "Расписание намазов на сегодня:\n"
        for prayer, time in prayer_times.items():
            schedule_text += f"{prayer}: {time}\n"
        schedule_text += f"\n{hijri_text}"
        await update.message.reply_text(schedule_text, reply_markup=REPLY_KEYBOARD)
        logging.info("Расписание отправлено %s: %s", chat_id, schedule_text)
    else:
        schedule_text = f"Расписание на сегодня недоступно.\n\n{hijri_text}"
        await update.message.reply_text(schedule_text, reply_markup=REPLY_KEYBOARD)
        logging.info("Расписание недоступно для %s", chat_id)

async def show_hadith(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка команды /hadith для отображения случайного хадиса"""
    chat_id = update.effective_chat.id
    logging.info("Команда /hadith от %s", chat_id)
    hadith = random.choice(HADITHS)
    message = f"Хадис из Сахих аль-Бухари или Сахих Муслима:\n{hadith['text']} ({hadith['reference']})"
    await update.message.reply_text(message, reply_markup=REPLY_KEYBOARD)
    logging.info("Хадис отправлен %s: %s", chat_id, message)

async def show_adhkar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка команды /adhkar для отображения утренних и вечерних азкаров"""
    chat_id = update.effective_chat.id
    logging.info("Команда /adhkar от %s", chat_id)
    adhkar_text = "Утренние и вечерние азкары (читать после Фаджр и Магриб):\n\n"
    for adhk in ADHKAR:
        adhkar_text += f"• {adhk['text']}\n  Повторять: {adhk['repetition']}\n  Источник: {adhk['source']}\n\n"
    adhkar_text += "Старайтесь читать азкары ежедневно для защиты и благословения!"
    await update.message.reply_text(adhkar_text, reply_markup=REPLY_KEYBOARD)
    logging.info("Азкары отправлены %s: %s", chat_id, adhkar_text)

async def show_islamic_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка команды /islamic_date для отображения текущей исламской даты"""
    chat_id = update.effective_chat.id
    logging.info("Команда /islamic_date от %s", chat_id)
    if islamic_date["day"] and islamic_date["month"] and islamic_date["year"]:
        message = f"Дата: {islamic_date['day']} {islamic_date['month']} {islamic_date['year']} Хиджры"
    else:
        message = "Дата недоступна"
    await update.message.reply_text(message, reply_markup=REPLY_KEYBOARD)
    logging.info("Дата отправлена %s: %s", chat_id, message)

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
    elif text == "Азкары":
        await show_adhkar(update, context)
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
            prayer_times.update({
                "Фаджр(Сабах)": "03:06",
                "Восход(Догъуш)": "04:53",
                "Зухр(Уйле)": "12:45",
                "Аср(Экинди)": "16:47",
                "Магриб(Акъшам)": "20:27",
                "Иша(Ятсы)": "22:15"
            })
            islamic_date.update({"day": "29", "month": "Зуль-къаде", "year": "1446"})
            logging.info("Тестовое расписание: %s", prayer_times)
            logging.info("Тестовая исламская дата: %s", islamic_date)
        schedule_prayer_notifications()
        schedule.every().day.at("21:01").do(  # Изменено на 21:01 UTC = 00:01 MSK
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
ptb.add_handler(CommandHandler("adhkar", show_adhkar))
ptb.add_handler(CommandHandler("islamic_date", show_islamic_date))
ptb.add_handler(CommandHandler("contact", contact_developer))
ptb.add_handler(CommandHandler("menu", show_menu))
ptb.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_buttons))

if __name__ == "__main__":
    import uvicorn
    logging.info("Запуск Uvicorn")
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
