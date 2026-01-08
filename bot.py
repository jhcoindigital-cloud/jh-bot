import asyncio
import json
import pandas as pd
import ta
import websockets
from telegram import Bot
from telegram.request import HTTPXRequest
from datetime import datetime, timedelta

# --- CONFIGURATION ---
TOKEN = "8349037970:AAHs6qJlHSaVnwA6PutPeppdyFB5zUnh9Bw"
USER_ID = 501795546
bot = Bot(token=TOKEN, request=HTTPXRequest(connect_timeout=30))

candles = []
stats = {"wins": 0, "losses": 0}
pending_trades = []

async def check_results(current_price):
    global stats
    now = datetime.now()
    for trade in pending_trades[:]:
        if now >= trade['expiry']:
            # Calcul du résultat
            win = (current_price > trade['entry']) if trade['type'] == "CALL" else (current_price < trade['entry'])

            if win: stats["wins"] += 1
            else: stats["losses"] += 1

            status = "✅ GAGNÉ" if win else "❌ PERDU"
            total = stats["wins"] + stats["losses"]
            wr = (stats["wins"] / total) * 100

            msg = (f"🏁 **RÉSULTAT**\n{status}\n"
                   f"Prix entrée: {trade['entry']}\n"
                   f"Prix sortie: {current_price}\n"
                   f"Score: {stats['wins']}W - {stats['losses']}L\n"
                   f"Winrate: {wr:.1f}%")
            await bot.send_message(chat_id=USER_ID, text=msg)
            pending_trades.remove(trade)

async def analyze_data(df):
    # Indicateurs
    stoch = ta.momentum.StochasticOscillator(df['h'], df['l'], df['c']).stoch().iloc[-1]
    macd = ta.trend.MACD(df['c'])
    m_line, s_line = macd.macd().iloc[-1], macd.macd_signal().iloc[-1]

    curr_p = df['c'].iloc[-1]
    signal = None

    if stoch < 20 and m_line > s_line: signal = "CALL"
    elif stoch > 80 and m_line < s_line: signal = "PUT"

    if signal:
        expiry = datetime.now() + timedelta(minutes=2)
        pending_trades.append({'entry': curr_p, 'type': signal, 'expiry': expiry})

        msg = (f"🎯 **SIGNAL TEMPS RÉEL**\n"
               f"Action: {signal}\n"
               f"Prix: {curr_p}\n"
               f"Stoch: {stoch:.1f}\n"
               f"⏳ Expire dans 2 min")
        await bot.send_message(chat_id=USER_ID, text=msg, parse_mode="Markdown")

async def binance_stream():
    global candles
    uri = "wss://stream.binance.com:9443/ws/eurusdt@kline_1m"
    async with websockets.connect(uri) as ws:
        print("✅ WebSocket Connecté - Flux Live Actif")
        while True:
            data = json.loads(await ws.recv())
            k = data['k']
            new_c = {'t':k['t'], 'o':float(k['o']), 'h':float(k['h']), 'l':float(k['l']), 'c':float(k['c'])}

            if not candles or candles[-1]['t'] != new_c['t']:
                candles.append(new_c)
            else:
                candles[-1] = new_c

            if len(candles) > 60: candles.pop(0)

            # Vérification des trades en cours à chaque seconde
            await check_results(new_c['c'])

            # Analyse à la clôture de la bougie
            if k['x']:
                await analyze_data(pd.DataFrame(candles))

async def main():
    while True:
        try:
            await binance_stream()
        except:
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())
