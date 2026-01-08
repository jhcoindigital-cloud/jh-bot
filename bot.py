import asyncio, json, os, websockets
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from flask import Flask
from threading import Thread

# --- SERVEUR WEB ---
app = Flask('')
@app.route('/')
def home(): return "Bot is Alive"
def run_web_server():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))

# --- CONFIGURATION ---
TOKEN = "8349037970:AAEE3AqgyQWiI6TBVIdrJ4xR0aqNgF5Z9PU" # Remplace bien ici !
USER_ID = 501795546
last_price = 0.0

def get_menu():
    keyboard = [[InlineKeyboardButton("📊 Stats", callback_data="stats"),
                 InlineKeyboardButton("💰 Prix Actuel", callback_data="price")]]
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Connexion Propre. Menu :", reply_markup=get_menu())

async def btn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    global last_price
    if query.data == "price":
        txt = f"💰 **EUR/USD** : `{last_price if last_price > 0 else 'Chargement...'}`"
        await query.edit_message_text(text=txt, reply_markup=get_menu(), parse_mode="Markdown")

async def binance():
    global last_price
    uri = "wss://stream.binance.com:443/ws/eurusdt@kline_1m"
    while True:
        try:
            async with websockets.connect(uri) as ws:
                while True:
                    data = json.loads(await ws.recv())
                    last_price = float(data['k']['c'])
        except: await asyncio.sleep(5)

async def main():
    Thread(target=run_web_server, daemon=True).start()
    app_tg = Application.builder().token(TOKEN).build()
    app_tg.add_handler(CommandHandler("start", start))
    app_tg.add_handler(CallbackQueryHandler(btn))
    
    await app_tg.initialize()
    await app_tg.start()
    # On vide les vieux messages
    await app_tg.updater.start_polling(drop_pending_updates=True)
    await binance()

if __name__ == "__main__":
    asyncio.run(main())
