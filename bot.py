import asyncio
import json
import pandas as pd
import ta
import websockets
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.error import BadRequest
from datetime import datetime
from flask import Flask
from threading import Thread
import os

# --- 1. SERVEUR WEB (POUR RENDER GRATUIT) ---
app = Flask('')
@app.route('/')
def home(): return "Bot is Running!"

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# --- 2. CONFIGURATION ---
# Sur Render, ajoute TELEGRAM_TOKEN dans "Environment Variables"
TOKEN = "8349037970:AAHs6qJlHSaVnwA6PutPeppdyFB5zUnh9Bw"
USER_ID = 501795546

candles = []
stats = {"wins": 0, "losses": 0}
last_price = 0.0
status_ws = "🔴 Déconnecté"

# --- 3. FONCTIONS DES BOUTONS ---

async def get_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton("📊 Voir les Stats", callback_data="stats"),
         InlineKeyboardButton("💰 Prix Actuel", callback_data="price")],
        [InlineKeyboardButton("📡 État du Serveur", callback_data="status")]
    ]
    return InlineKeyboardMarkup(keyboard)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎮 **Tableau de Bord interactif**\nChoisissez une option :",
        reply_markup=await get_menu_keyboard(),
        parse_mode="Markdown"
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    global stats, last_price, status_ws
    now = datetime.now().strftime("%H:%M:%S")
    
    if query.data == "stats":
        total = stats["wins"] + stats["losses"]
        wr = (stats["wins"] / total * 100) if total > 0 else 0
        txt = f"📊 **Statistiques ({now})**\n✅ Gains : {stats['wins']}\n❌ Pertes : {stats['losses']}\n📈 Winrate : {wr:.1f}%"
    
    elif query.data == "price":
        txt = f"💰 **Prix EUR/USD ({now})**\nActuel : `{last_price}`"
        
    elif query.data == "status":
        txt = f"📡 **État du Serveur ({now})**\nFlux WS : {status_ws}\nServeur : 🟢 Online"

    try:
        await query.edit_message_text(
            text=txt, 
            reply_markup=await get_menu_keyboard(), 
            parse_mode="Markdown"
        )
    except BadRequest as e:
        if "Message is not modified" not in str(e):
            print(f"Erreur Telegram: {e}")

# --- 4. LOGIQUE DE TRADING ---

async def analyze_data(application, df):
    global last_price
    stoch = ta.momentum.StochasticOscillator(df['h'], df['l'], df['c']).stoch().iloc[-1]
    macd = ta.trend.MACD(df['c'])
    m_line, s_line = macd.macd().iloc[-1], macd.macd_signal().iloc[-1]
    
    curr_p = df['c'].iloc[-1]
    signal = None
    
    if stoch < 20 and m_line > s_line: signal = "CALL"
    elif stoch > 80 and m_line < s_line: signal = "PUT"
    
    if signal:
        msg = f"🎯 **NOUVEAU SIGNAL**\nAction: {signal}\nPrix: `{curr_p}`\nStoch: `{stoch:.1f}`"
        await application.bot.send_message(chat_id=USER_ID, text=msg)

async def binance_stream(application):
    global candles, last_price, status_ws
    uri = "wss://stream.binance.com:9443/ws/eurusdt@kline_1m"
    async with websockets.connect(uri) as ws:
        status_ws = "🟢 Connecté"
        while True:
            message = await ws.recv()
            data = json.loads(message)
            k = data['k']
            last_price = float(k['c'])
            
            new_c = {'t':k['t'], 'o':float(k['o']), 'h':float(k['h']), 'l':float(k['l']), 'c':last_price}
            if not candles or candles[-1]['t'] != new_c['t']:
                candles.append(new_c)
            else:
                candles[-1] = new_c
            
            if len(candles) > 60: candles.pop(0)
            if k['x']: 
                await analyze_data(application, pd.DataFrame(candles))

# --- 5. LANCEMENT ---

async def main():
    Thread(target=run_web_server, daemon=True).start()

    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("menu", start_command))
    application.add_handler(CallbackQueryHandler(button_handler))

    await application.initialize()
    await application.start()
    await application.updater.start_polling()

    print("🚀 Bot Lancé")
    
    while True:
        try:
            await binance_stream(application)
        except Exception as e:
            status_ws = "🔴 Reconnexion..."
            print(f"Erreur Stream: {e}")
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main()) 


