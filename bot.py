import asyncio, json, os, websockets
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from datetime import datetime
from flask import Flask
from threading import Thread

# --- SERVEUR WEB (Pour Render) ---
app = Flask('')
@app.route('/')
def home(): return "Bot is Alive"
def run_web_server():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))

# --- CONFIGURATION ---
# Nouveau Token mis à jour
TOKEN = "8349037970:AAHs6qJlHSaVnwA6PutPeppdyFB5zUnh9Bw"
USER_ID = 501795546
last_price = 0.0
status_ws = "🔴 Déconnecté"

async def get_menu():
    keyboard = [
        [InlineKeyboardButton("📊 Stats", callback_data="stats"),
         InlineKeyboardButton("💰 Prix Actuel", callback_data="price")],
        [InlineKeyboardButton("📡 État du Serveur", callback_data="status")]
    ]
    return InlineKeyboardMarkup(keyboard)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    global last_price, status_ws
    now = datetime.now().strftime("%H:%M:%S")
    
    if query.data == "price":
        p_text = f"{last_price}" if last_price > 0 else "Attente du flux..."
        txt = f"💰 **Prix EUR/USD ({now})**\nActuel : `{p_text}`"
    elif query.data == "status":
        txt = f"📡 **État du Serveur ({now})**\nFlux WS : {status_ws}\nServeur : 🟢 Online"
    else:
        txt = f"📊 **Statistiques**\nSession : 0W - 0L"
    
    await query.edit_message_text(text=txt, reply_markup=await get_menu(), parse_mode="Markdown")

async def binance_stream():
    global last_price, status_ws
    uri = "wss://stream.binance.com:9443/ws/eurusdt@kline_1m"
    while True:
        try:
            async with websockets.connect(uri, ping_interval=20, ping_timeout=20) as ws:
                status_ws = "🟢 Connecté"
                while True:
                    res = await ws.recv()
                    data = json.loads(res)
                    last_price = float(data['k']['c'])
        except Exception as e:
            status_ws = "🔴 Reconnexion..."
            await asyncio.sleep(5)

async def main():
    # 1. Lancer le serveur web pour que Render reste actif
    Thread(target=run_web_server, daemon=True).start()
    
    # 2. Initialiser le Bot avec le nouveau Token
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("menu", lambda u, c: u.message.reply_text("🎮 Menu de trading", reply_markup=asyncio.run(get_menu()))))
    application.add_handler(CallbackQueryHandler(button_handler))
    
    await application.initialize()
    await application.start()
    
    # LA SOLUTION : drop_pending_updates=True tue les anciennes sessions en conflit
    await application.updater.start_polling(drop_pending_updates=True)
    
    await application.bot.send_message(chat_id=USER_ID, text="✅ **Bot activé avec le nouveau Token !**\nLe flux Binance se connecte...")
    
    # 3. Lancer le flux de prix
    await binance_stream()

if __name__ == "__main__":
    asyncio.run(main())

