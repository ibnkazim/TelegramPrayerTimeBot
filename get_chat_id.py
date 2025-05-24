from telegram import Bot
import asyncio

async def get_chat_id():
    bot = Bot(token="7402773153:AAFxzD6OGtPEdsH87l9v_sfv6_3nOlg3PD4")
    updates = await bot.get_updates()
    for update in updates:
        print(f"Chat ID: {update.message.chat.id}")

asyncio.run(get_chat_id())

#на случай если нужно будет добавить бота в чат