import asyncio, json, os, websockets
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from flask import Flask
from threading import Thread

# --- SERVEUR WEB (Pour Render) ---
app = Flask('')
@app.route('/')
def home(): return "Bot is Alive"
def run_web_server():
    app.run(host='0.0.0.0', port=10000)

# --- CONFIGURATION ---
TOKEN = "8349037970:AAHmHCSpe6lml9bIWlxPdFZ3MHPlviIm5CQ" # <--- TON NOUVEAU TOKEN ICI
USER_ID = 501795546
last_price = "En attente..."

# --- INTERFACE ---
def get_menu():
    return InlineKeyboardMarkup([[InlineKeyboardButton("💰 Voir le Prix EUR/USD", callback_data="p")]])

async def start(u: Update, c: ContextTypes.DEFAULT_TYPE):
    await u.message.reply_text("✅ Nouveau Token activé ! Le bot est prêt.", reply_markup=get_menu())

async def btn(u: Update, c: ContextTypes.DEFAULT_TYPE):
    query = u.callback_query
    await query.answer()
    global last_price
    await query.edit_message_text(f"📊 **Prix Actuel** : `{last_price}`", reply_markup=get_menu(), parse_mode="Markdown")

# --- FLUX BINANCE ---
async def binance():
    global last_price
    uri = "wss://stream.binance.com/ws/eurusdt@kline_1m"
    while True:
        try:
            async with websockets.connect(uri, ping_interval=20) as ws:
                while True:
                    msg = await ws.recv()
                    last_price = json.loads(msg)['k']['c']
        except:
            await asyncio.sleep(5)

# --- LANCEMENT ---
async def main():
    # Lancer le serveur web
    Thread(target=run_web_server, daemon=True).start()
    
    # Configuration du bot
    bot = Application.builder().token(TOKEN).build()
    bot.add_handler(CommandHandler("start", start))
    bot.add_handler(CallbackQueryHandler(btn))
    
    await bot.initialize()
    await bot.start()
    
    # Nettoyage des anciennes sessions (essentiel pour éviter le Conflict)
    await bot.updater.start_polling(drop_pending_updates=True)
    
    print("🚀 BOT DÉMARRÉ AVEC LE NOUVEAU TOKEN")
    
    # Lancement du flux Binance
    await binance()

if __name__ == "__main__":
    asyncio.run(main())
