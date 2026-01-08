import asyncio, json, os, websockets
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from flask import Flask
from threading import Thread

# --- SERVEUR WEB POUR RENDER ---
app = Flask('')
@app.route('/')
def home(): return "Bot is Online"
def run_web_server():
    app.run(host='0.0.0.0', port=10000)

# --- CONFIGURATION ---
# COLLE TON NOUVEAU TOKEN ICI
TOKEN = "8349037970:AAHmHCSpe6lml9bIWlxPdFZ3MHPlviIm5CQ" 
USER_ID = 501795546
last_price = "0.0"

async def start(u: Update, c: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("💰 Prix EUR/USD", callback_data="p")]]
    await u.message.reply_text("✅ Bot connecté ! Cliquez pour le prix :", reply_markup=InlineKeyboardMarkup(keyboard))

async def btn(u: Update, c: ContextTypes.DEFAULT_TYPE):
    query = u.callback_query
    await query.answer()
    global last_price
    await query.edit_message_text(f"📊 **Prix Actuel** : `{last_price}`", 
                                  reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Actualiser", callback_data="p")]]), 
                                  parse_mode="Markdown")

async def binance():
    global last_price
    uri = "wss://stream.binance.com:443/ws/eurusdt@kline_1m"
    while True:
        try:
            async with websockets.connect(uri) as ws:
                while True:
                    data = json.loads(await ws.recv())
                    last_price = data['k']['c']
        except:
            await asyncio.sleep(5)

async def main():
    Thread(target=run_web_server, daemon=True).start()
    bot = Application.builder().token(TOKEN).build()
    bot.add_handler(CommandHandler("start", start))
    bot.add_handler(CallbackQueryHandler(btn))
    
    await bot.initialize()
    await bot.start()
    # Cette ligne tue le conflit Telegram
    await bot.updater.start_polling(drop_pending_updates=True)
    await binance()

if __name__ == "__main__":
    asyncio.run(main())
