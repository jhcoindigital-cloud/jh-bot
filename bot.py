import asyncio, json, os, websockets
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from datetime import datetime
from flask import Flask
from threading import Thread

# --- SERVEUR WEB ---
app = Flask('')
@app.route('/')
def home(): return "Bot is Alive"
def run_web_server():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))

# --- CONFIGURATION ---
TOKEN = "8553165413:AAE8CUjph44w-nmkpcRnlnz53EFk-V4vEOM"
USER_ID = 501795546
last_price = 0.0
status_ws = "🔴 Déconnecté"

# --- INTERFACE ---
def get_menu():
    keyboard = [
        [InlineKeyboardButton("📊 Stats", callback_data="stats"),
         InlineKeyboardButton("💰 Prix Actuel", callback_data="price")],
        [InlineKeyboardButton("📡 État du Serveur", callback_data="status")]
    ]
    return InlineKeyboardMarkup(keyboard)

async def start_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🎮 Menu de trading actif :", reply_markup=get_menu())

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    global last_price, status_ws
    now = datetime.now().strftime("%H:%M:%S")
    
    if query.data == "price":
        p_text = f"{last_price}" if last_price > 0 else "Récupération..."
        txt = f"💰 **Prix EUR/USD ({now})**\nActuel : `{p_text}`"
    elif query.data == "status":
        txt = f"📡 **État du Serveur ({now})**\nFlux WS : {status_ws}\nServeur : 🟢 Online"
    else:
        txt = f"📊 **Statistiques**\nSession : 0W - 0L"
    
    await query.edit_message_text(text=txt, reply_markup=get_menu(), parse_mode="Markdown")

# --- FLUX BINANCE ---
async def binance_stream():
    global last_price, status_ws
    uri = "wss://stream.binance.com:9443/ws/eurusdt@kline_1m"
    while True:
        try:
            async with websockets.connect(uri, ping_interval=20) as ws:
                status_ws = "🟢 Connecté"
                while True:
                    res = await ws.recv()
                    data = json.loads(res)
                    last_price = float(data['k']['c'])
        except:
            status_ws = "🔴 Reconnexion..."
            await asyncio.sleep(5)

# --- LANCEMENT ---
async def main():
    Thread(target=run_web_server, daemon=True).start()
    
    application = Application.builder().token(TOKEN).build()
    
    # Correction de l'erreur asyncio : on utilise des fonctions directes
    application.add_handler(CommandHandler("menu", start_menu))
    application.add_handler(CommandHandler("start", start_menu))
    application.add_handler(CallbackQueryHandler(button_handler))
    
    await application.initialize()
    await application.start()
    # Nettoyage des anciennes requêtes pour éviter le conflit Telegram
    await application.updater.start_polling(drop_pending_updates=True)
    
    print("🚀 Bot prêt")
    try:
        await application.bot.send_message(chat_id=USER_ID, text="✅ **Système Redémarré**\nLe menu est maintenant opérationnel.")
    except: pass
    
    await binance_stream()

if __name__ == "__main__":
    asyncio.run(main())
