import asyncio
import json
import pandas as pd
import ta
import websockets
from telegram import Bot
from telegram.request import HTTPXRequest
from datetime import datetime, timedelta
from flask import Flask
from threading import Thread
import os

# --- PARTIE FAUX SERVEUR WEB POUR RENDER ---
app = Flask('')

@app.route('/')
def home():
    return "Bot is alive!"

def run_web_server():
    # Render donne un port spécifique, on doit l'utiliser
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# --- CONFIGURATION DU BOT ---
TOKEN = "8349037970:AAHs6qJlHSaVnwA6PutPeppdyFB5zUnh9Bw"
USER_ID = 501795546
bot = Bot(token=TOKEN, request=HTTPXRequest(connect_timeout=30))

candles = []

async def analyze_data(df):
    stoch = ta.momentum.StochasticOscillator(df['h'], df['l'], df['c']).stoch().iloc[-1]
    macd = ta.trend.MACD(df['c'])
    m_line, s_line = macd.macd().iloc[-1], macd.macd_signal().iloc[-1]
    
    curr_p = df['c'].iloc[-1]
    signal = None
    
    if stoch < 20 and m_line > s_line: signal = "🔵 CALL"
    elif stoch > 80 and m_line < s_line: signal = "🔴 PUT"
    
    if signal:
        msg = f"🎯 **SIGNAL LIVE**\nAction: {signal}\nPrix: {curr_p}"
        await bot.send_message(chat_id=USER_ID, text=msg)

async def binance_stream():
    uri = "wss://stream.binance.com:9443/ws/eurusdt@kline_1m"
    async with websockets.connect(uri) as ws:
        print("✅ Flux Connecté")
        while True:
            data = json.loads(await ws.recv())
            k = data['k']
            new_c = {'t':k['t'], 'o':float(k['o']), 'h':float(k['h']), 'l':float(k['l']), 'c':float(k['c'])}
            if not candles or candles[-1]['t'] != new_c['t']:
                candles.append(new_c)
            else:
                candles[-1] = new_c
            if len(candles) > 60: candles.pop(0)
            if k['x']:
                await analyze_data(pd.DataFrame(candles))

async def main():
    # Lancement du serveur web en arrière-plan
    Thread(target=run_web_server).start()
    
    while True:
        try:
            await binance_stream()
        except:
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())
