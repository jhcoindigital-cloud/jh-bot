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
current_strategy = "FRACTALE_3"
high_precedent = 0.0
highs_history = []
signal_envoye = False
binance_status = "❌ Déconnecté"

# ================= SERVEUR WEB (KEEP-ALIVE) =================
app = Flask(__name__)
@app.route("/")
def home(): return "Bot Binary Anticipation Actif ✅"

def run_web(): app.run(host="0.0.0.0", port=10000)

# ================= NOTIFICATION DE DÉPLOIEMENT =================
async def notify_deploy(app_tg):
    """ Envoie un message dès que le bot est prêt sur Render """
    try:
        await asyncio.sleep(2) # Petit délai pour laisser le temps au bot de s'initialiser
        await app_tg.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text="🚀 **Bot déployé avec succès sur Render !**\n\nLe système d'analyse de trading est actif et surveille le marché. Tapez /settings pour configurer."
        )
        print("✅ Notification de déploiement envoyée.")
    except Exception as e:
        print(f"⚠️ Erreur notification déploiement : {e}")

# ================= LOGIQUE D'ANTICIPATION =================
def calculer_anticipation(prix_actuel, niveau_casse, strategie):
    ecart = ((prix_actuel - niveau_casse) / niveau_casse) * 100
    if strategie == "FRACTALE_5":
        exp, confiance = "3-5 MIN", "ÉLEVÉE" if ecart > 0.02 else "MOYENNE"
    elif strategie == "FRACTALE_3":
        exp, confiance = "2 MIN", "MOYENNE" if ecart > 0.01 else "FAIBLE"
    else:
        exp, confiance = "1 MIN", "FAIBLE (Scalping)"
    return exp, confiance, ecart

# ================= TELEGRAM INTERFACE =================
async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🚀 Bougie Précédente (1m)", callback_data='STRAT_SIMPLE')],
        [InlineKeyboardButton("💎 Fractale 3 Bougies (2m)", callback_data='STRAT_3')],
        [InlineKeyboardButton("🏆 Fractale 5 Bougies (3-5m)", callback_data='STRAT_5')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(f"⚙️ **Configuration**\nMode actuel : `{current_strategy}`\nChoisissez votre stratégie :", 
                                  reply_markup=reply_markup, parse_mode="Markdown")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global current_strategy, signal_envoye
    query = update.callback_query
    await query.answer()
    mapping = {'STRAT_SIMPLE': "SIMPLE", 'STRAT_3': "FRACTALE_3", 'STRAT_5': "FRACTALE_5"}
    current_strategy = mapping.get(query.data, "FRACTALE_3")
    signal_envoye = False
    await query.edit_message_text(text=f"✅ Stratégie : *{current_strategy}* activée.", parse_mode="Markdown")

# ================= ANALYSE & WEBSOCKET =================
async def binance_ws(app_tg):
    global last_price, binance_status, high_precedent, signal_envoye, highs_history
    uri = "wss://stream.binance.com:443/ws/eurusdt@kline_1m"

    while True:
        try:
            async with websockets.connect(uri) as ws:
                binance_status = "✅ Connecté"
                while True:
                    data = json.loads(await ws.recv())
                    k = data['k']
                    price_actuel = float(k['c'])
                    last_price = f"{price_actuel:.5f}"
                    
                    if k['x']: # Bougie Fermée
                        val_high = float(k['h'])
                        highs_history.append(val_high)
                        if len(highs_history) > 5: highs_history.pop(0)

                        if current_strategy == "SIMPLE":
                            high_precedent = val_high
                        elif current_strategy == "FRACTALE_3" and len(highs_history) >= 3:
                            h = highs_history[-3:]
                            if h[1] > h[0] and h[1] > h[2]: high_precedent = h[1]
                        elif current_strategy == "FRACTALE_5" and len(highs_history) == 5:
                            h = highs_history
                            if h[2] > h[0] and h[2] > h[1] and h[2] > h[3] and h[2] > h[4]: high_precedent = h[2]
                        
                        signal_envoye = False

                    if high_precedent > 0 and price_actuel > high_precedent and not signal_envoye:
                        exp, conf, pwr = calculer_anticipation(price_actuel, high_precedent, current_strategy)
                        message = (
                            f"🔔 **SIGNAL D'ACHAT BINAIRE**\n\n"
                            f"📈 Stratégie : `{current_strategy}`\n"
                            f"🎯 Niveau cassé : `{high_precedent:.5f}`\n"
                            f"💰 Prix actuel : `{price_actuel:.5f}`\n"
                            f"⚡ Force : `+{pwr:.3f}%`\n\n"
                            f"⏳ **ANTICIPATION :**\n"
                            f"👉 Expiration : **{exp}**\n"
                            f"🛡️ Confiance : **{conf}**"
                        )
                        await app_tg.bot.send_message(chat_id=ADMIN_CHAT_ID, text=message, parse_mode="Markdown")
                        signal_envoye = True

        except Exception:
            binance_status = "❌ Déconnecté"
            await asyncio.sleep(5)

# ================= LANCEMENT =================
def main():
    Thread(target=run_web, daemon=True).start()
    app_tg = Application.builder().token(TOKEN).build()
    
    app_tg.add_handler(CommandHandler("start", lambda u, c: u.message.reply_text("Bot prêt. /settings")))
    app_tg.add_handler(CommandHandler("settings", settings))
    app_tg.add_handler(CallbackQueryHandler(button_handler))

    loop = asyncio.get_event_loop()
    
    # --- LES TACHES ASYNCHRONES ---
    loop.create_task(binance_ws(app_tg))
    loop.create_task(notify_deploy(app_tg)) # <--- LA NOTIFICATION ICI
    
    print("🚀 Bot Options Binaires en ligne")
    app_tg.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
