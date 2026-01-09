import asyncio
import json
import os
import websockets
from threading import Thread
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler

# ================= CONFIGURATION =================
TOKEN = os.getenv("BOT_TOKEN", "REMPLACE_PAR_TON_TOKEN")
ADMIN_CHAT_ID = os.getenv("CHAT_ID", "REMPLACE_PAR_TON_CHAT_ID")

last_price = "⏳ Connexion..."
current_strategy = "FRACTALE_3" # Mode par défaut
target_high = 0.0
target_low = 0.0
highs_history = []
lows_history = []
signal_envoye_call = False
signal_envoye_put = False
binance_status = "❌ Déconnecté"

# ================= SERVEUR WEB (KEEP-ALIVE) =================
app = Flask(__name__)
@app.route("/")
def home(): return "Bot Trading Actif ✅"

def run_web(): app.run(host="0.0.0.0", port=10000)

# ================= LOGIQUE D'ANALYSE PAR CATÉGORIE =================
async def analyser_marche(app_tg, prix_actuel):
    global target_high, target_low, signal_envoye_call, signal_envoye_put
    
    # 1. Vérifier la cassure de Haut (CALL)
    if target_high > 0 and prix_actuel > target_high and not signal_envoye_call:
        exp = "1m" if current_strategy == "SIMPLE" else "2m" if current_strategy == "FRACTALE_3" else "5m"
        msg = f"🟢 **SIGNAL CALL ({current_strategy})**\n\n🎯 Niveau : `{target_high:.5f}`\n💰 Prix : `{prix_actuel:.5f}`\n⏳ Exp : **{exp}**"
        await app_tg.bot.send_message(chat_id=ADMIN_CHAT_ID, text=msg, parse_mode="Markdown")
        signal_envoye_call = True

    # 2. Vérifier la cassure de Bas (PUT)
    if target_low > 0 and prix_actuel < target_low and not signal_envoye_put:
        exp = "1m" if current_strategy == "SIMPLE" else "2m" if current_strategy == "FRACTALE_3" else "5m"
        msg = f"🔴 **SIGNAL PUT ({current_strategy})**\n\n🎯 Niveau : `{target_low:.5f}`\n💰 Prix : `{prix_actuel:.5f}`\n⏳ Exp : **{exp}**"
        await app_tg.bot.send_message(chat_id=ADMIN_CHAT_ID, text=msg, parse_mode="Markdown")
        signal_envoye_put = True

# ================= BINANCE WEBSOCKET =================
async def binance_ws(app_tg):
    global last_price, binance_status, target_high, target_low, highs_history, lows_history
    global signal_envoye_call, signal_envoye_put

    uri = "wss://stream.binance.com:443/ws/eurusdt@kline_1m"
    while True:
        try:
            async with websockets.connect(uri) as ws:
                binance_status = "✅ Connecté"
                while True:
                    data = json.loads(await ws.recv())
                    k = data['k']
                    prix_actuel = float(k['c'])
                    last_price = f"{prix_actuel:.5f}"
                    
                    if k['x']: # Quand la bougie ferme
                        highs_history.append(float(k['h']))
                        lows_history.append(float(k['l']))
                        if len(highs_history) > 5:
                            highs_history.pop(0)
                            lows_history.pop(0)

                        # MISE À JOUR DU NIVEAU SELON LA CATÉGORIE CHOISIE
                        if current_strategy == "SIMPLE":
                            target_high = highs_history[-1]
                            target_low = lows_history[-1]
                        
                        elif current_strategy == "FRACTALE_3" and len(highs_history) >= 3:
                            h, l = highs_history[-3:], lows_history[-3:]
                            if h[1] > h[0] and h[1] > h[2]: target_high = h[1]
                            if l[1] < l[0] and l[1] < l[2]: target_low = l[1]
                        
                        elif current_strategy == "FRACTALE_5" and len(highs_history) == 5:
                            h, l = highs_history, lows_history
                            if h[2] > h[0] and h[2] > h[1] and h[2] > h[3] and h[2] > h[4]: target_high = h[2]
                            if l[2] < l[0] and l[2] < l[1] and l[2] < l[3] and l[2] < l[4]: target_low = l[2]
                        
                        signal_envoye_call = False
                        signal_envoye_put = False

                    # Analyse en temps réel du prix
                    await analyser_marche(app_tg, prix_actuel)

        except Exception:
            binance_status = "❌ Déconnecté"
            await asyncio.sleep(5)

# ================= INTERFACE TELEGRAM =================
async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🚀 Simple (1m)", callback_data='SET_SIMPLE')],
        [InlineKeyboardButton("💎 Fractale 3 (2m)", callback_data='SET_3')],
        [InlineKeyboardButton("🏆 Fractale 5 (5m)", callback_data='SET_5')]
    ]
    await update.message.reply_text(f"Mode actuel : {current_strategy}\nChoisissez la catégorie de signaux à recevoir :", 
                                  reply_markup=InlineKeyboardMarkup(keyboard))

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global current_strategy, signal_envoye_call, signal_envoye_put, target_high, target_low
    query = update.callback_query
    await query.answer()
    
    mapping = {'SET_SIMPLE': "SIMPLE", 'SET_3': "FRACTALE_3", 'SET_5': "FRACTALE_5"}
    current_strategy = mapping.get(query.data)
    
    # Reset pour forcer le nouveau calcul au prochain kline
    target_high = target_low = 0.0
    signal_envoye_call = signal_envoye_put = False
    
    await query.edit_message_text(text=f"✅ Catégorie activée : **{current_strategy}**\nLe bot attend la prochaine bougie pour définir les cibles.", parse_mode="Markdown")

async def post_init(application: Application):
    asyncio.create_task(binance_ws(application))
    await application.bot.send_message(chat_id=ADMIN_CHAT_ID, text="🚀 Bot déployé. Tapez /settings pour choisir votre stratégie.")

# ================= MAIN =================
def main():
    Thread(target=run_web, daemon=True).start()
    app_tg = Application.builder().token(TOKEN).post_init(post_init).build()
    app_tg.add_handler(CommandHandler("settings", settings))
    app_tg.add_handler(CallbackQueryHandler(button_handler))
    app_tg.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
