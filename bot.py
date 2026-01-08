import asyncio, json, os, websockets
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from flask import Flask
from threading import Thread

# --- MINI SERVEUR POUR RENDER ---
app = Flask('')
@app.route('/')
def home(): return "OK"
def run_web_server():
    app.run(host='0.0.0.0', port=10000)

# --- CONFIG ---
TOKEN = "8553165413:AAE8CUjph44w-nmkpcRnlnz53EFk-V4vEOM"
USER_ID = 501795546
last_price = "En attente..."

def get_menu():
    return InlineKeyboardMarkup([[InlineKeyboardButton("💰 Voir le Prix", callback_data="p")]])

async def start(u: Update, c: ContextTypes.DEFAULT_TYPE):
    await u.message.reply_text("✅ Connecté ! Appuie pour le prix :", reply_markup=get_menu())

async def btn(u: Update, c: ContextTypes.DEFAULT_TYPE):
    query = u.callback_query
    await query.answer()
    global last_price
    await query.edit_message_text(f"📊 **Prix EUR/USD** : `{last_price}`", reply_markup=get_menu(), parse_mode="Markdown")

async def binance():
    global last_price
    # On utilise l'adresse de secours sans port spécifique
    uri = "wss://stream.binance.com/ws/eurusdt@kline_1m"
    while True:
        try:
            async with websockets.connect(uri, ping_interval=20) as ws:
                print("📡 Flux Binance : OUVERT")
                while True:
                    msg = await ws.recv()
                    last_price = float(json.loads(msg)['k']['c'])
        except Exception as e:
            print(f"⚠️ Erreur Binance : {e}")
            await asyncio.sleep(5)

async def main():
    Thread(target=run_web_server, daemon=True).start()
    bot = Application.builder().token(TOKEN).build()
    bot.add_handler(CommandHandler("start", start))
    bot.add_handler(CallbackQueryHandler(btn))
    
    await bot.initialize()
    await bot.start()
    await bot.updater.start_polling(drop_pending_updates=True)
    print("🚀 BOT DÉMARRÉ SANS CONFLIT")
    await binance()

if __name__ == "__main__":
    asyncio.run(main())
