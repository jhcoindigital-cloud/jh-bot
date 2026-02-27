import urllib.request
import urllib.parse
import json
import asyncio
import time
import csv
from io import StringIO
import requests
from config import CONFIG, STATS, TELEGRAM_TOKEN, CHAT_ID, MODES_CONFIG

def send_tg_sync(text, reply_markup=None, retries=3):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=data)
    req.add_header('Content-Type', 'application/json')
    
    # Boucle pour réessayer d'envoyer le message en cas de coupure internet
    for attempt in range(retries):
        try:
            # On augmente le timeout à 15 secondes pour les connexions lentes
            with urllib.request.urlopen(req, timeout=15) as response:
                return json.loads(response.read().decode())
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(1)  # On attend 1 seconde et on réessaie
                continue
            else:
                print(f"⚠️ Erreur d'envoi Telegram (après {retries} tentatives) : {e}")
                return None

async def send_tg(text, reply_markup=None):
    return await asyncio.to_thread(send_tg_sync, text, reply_markup)

async def send_csv():
    output = StringIO()
    # 1. Utilisation du point-virgule pour Excel FR
    writer = csv.writer(output, delimiter=';')
    
    # --- Petite fonction pour formater les chiffres avec une virgule ---
    def fmt(val, decimals=2, sign=False):
        if isinstance(val, (int, float)):
            fmt_str = f"{val:+.{decimals}f}" if sign else f"{val:.{decimals}f}"
            return fmt_str.replace('.', ',')
        return str(val)

    # ================== RÉSUMÉ GLOBAL ==================
    writer.writerow(["Catégorie", "Statistique", "Valeur"])
    
    writer.writerow(["Solde & Profit", "Solde Initial", f"{fmt(STATS['start_balance'])}$"])
    writer.writerow(["Solde & Profit", "Solde Actuel", f"{fmt(STATS['current_balance'])}$"])
    profit = STATS["current_balance"] - STATS["start_balance"]
    profit_pct = (profit / STATS["start_balance"] * 100) if STATS["start_balance"] > 0 else 0.0
    writer.writerow(["Solde & Profit", "Profit Net", f"{fmt(profit, sign=True)}$ ({fmt(profit_pct, 1, sign=True)}%)"])
    writer.writerow(["Solde & Profit", "Profit du Jour", f"{fmt(STATS['daily_profit'], sign=True)}$"])
    writer.writerow(["Solde & Profit", "Chiffre d'Affaires", f"{fmt(STATS['total_turnover'])}$"])
    writer.writerow(["Solde & Profit", "Max Drawdown", f"-{fmt(STATS['max_drawdown'])}$"])
    writer.writerow(["Solde & Profit", "Max Drawdown %", f"-{fmt(STATS['max_drawdown_pct'], 1)}%"])
    
    total_trades = STATS.get("wins", 0) + STATS.get("losses", 0)
    winrate = (STATS.get("wins", 0) / total_trades * 100) if total_trades > 0 else 0.0
    writer.writerow(["Performance Globale", "Wins", STATS.get("wins", 0)])
    writer.writerow(["Performance Globale", "Losses", STATS.get("losses", 0)])
    writer.writerow(["Performance Globale", "Winrate", f"{fmt(winrate, 1)}%"])
    writer.writerow(["Performance Globale", "Total Trades", total_trades])
    streak_text = f"{STATS.get('win_streak', 0)} wins consécutifs" if STATS.get("win_streak", 0) > 0 else f"{STATS.get('loss_streak', 0)} pertes consécutives"
    writer.writerow(["Performance Globale", "Streak Actuel", streak_text])
    
    profit_factor = (STATS.get("total_gross_profit", 0) / abs(STATS.get("total_gross_loss", 1))) if STATS.get("total_gross_loss", 0) != 0 else 0.0
    avg_win = (STATS.get("total_gross_profit", 0) / STATS.get("wins", 1)) if STATS.get("wins", 0) > 0 else 0.0
    avg_loss = (STATS.get("total_gross_loss", 0) / STATS.get("losses", 1)) if STATS.get("losses", 0) > 0 else 0.0
    risk_reward = avg_win / abs(avg_loss) if avg_loss != 0 else 0.0
    writer.writerow(["Risk & Stats", "Profit Factor", fmt(profit_factor)])
    writer.writerow(["Risk & Stats", "Risk/Reward Ratio", f"{fmt(risk_reward)}:1"])
    writer.writerow(["Risk & Stats", "Gain Moyen", f"{fmt(avg_win, sign=True)}$"])
    writer.writerow(["Risk & Stats", "Perte Moyenne", f"{fmt(avg_loss, sign=True)}$"])
    
    writer.writerow(["Indicateurs Actuels", "EMA", fmt(STATS.get('ema_val', 0), 5)])
    writer.writerow(["Indicateurs Actuels", f"RSI {CONFIG.get('rsi_period', 14)}", fmt(STATS.get('rsi_val', 0))])
    
    # ================== STATS PAR STRATÉGIE ==================
    writer.writerow([])
    writer.writerow(["STRATÉGIE", "WINS", "LOSSES", "WINRATE %", "PROFIT NET ($)"])
    for s, data in STATS.get("strategy_stats", {}).items():
        s_trades = data["wins"] + data["losses"]
        s_winrate = (data["wins"] / s_trades * 100) if s_trades > 0 else 0.0
        writer.writerow([s, data["wins"], data["losses"], fmt(s_winrate, 1), fmt(data['profit'], sign=True)])
    
    # ================== HISTORIQUE DES TRADES ==================
    writer.writerow([])
    writer.writerow(["HISTORIQUE DES TRADES"])
    writer.writerow([
        "Date-Heure", "Actif", "Direction", "Stratégie", "Mise ($)",
        "Profit/Perte ($)", "Résultat", "EMA au signal", "RSI au signal"
    ])
    
    if not STATS.get("trade_history"):
        writer.writerow(["—", "—", "—", "Aucun trade enregistré", "—", "—", "—", "—", "—"])
    else:
        for trade in STATS["trade_history"]:
            writer.writerow([
                trade.get('time', '—'),
                trade.get('actif', 'Inconnu'),
                trade.get('direction', '—').upper(),
                trade.get('strategy', '—'),
                fmt(trade.get('amount', 0)),
                fmt(trade.get('profit', 0), sign=True),
                trade.get('outcome', '—'),
                fmt(trade.get('ema_at_trade', 0), 5),
                fmt(trade.get('rsi_at_trade', 0))
            ])

    # 3. Format 'utf-8-sig' obligatoire pour forcer Excel à lire les accents
    csv_data = output.getvalue().encode('utf-8-sig')
    
    # Nom du fichier dynamique avec la date du jour
    nom_fichier = f"Rapport_JHBot_{time.strftime('%Y-%m-%d_%Hh%M')}.csv"
    
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendDocument"
    files = {'document': (nom_fichier, csv_data, 'text/csv')}
    data = {
        'chat_id': CHAT_ID, 
        'caption': '📊 <b>Rapport détaillé JHBot PRO</b>\n<i>Astuce : Ouvrez ce fichier sur un PC avec Excel. Les colonnes et les virgules s\'afficheront parfaitement !</i>',
        'parse_mode': 'HTML'
    }
    
    try:
        r = await asyncio.to_thread(requests.post, url, files=files, data=data)
        if r.status_code == 200:
            await send_tg("✅ Export CSV généré et envoyé avec succès !")
        else:
            await send_tg(f"❌ Erreur Telegram lors de l'envoi du CSV (code {r.status_code})")
    except Exception as e:
        await send_tg("❌ Erreur de connexion lors de la création du CSV.")
        print(f"Erreur d'envoi CSV : {e}")

def main_keyboard():
    from config import CONFIG
    keyboard = [
        [{"text": "📊 Rapport"}, {"text": "🎯 Stratégies"}],
        [{"text": "📈 EMA Filter"}, {"text": "📉 RSI Filter"}],
        [{"text": "🌐 Menu Multi-Actifs"}, {"text": "🎯 Limite Profit Objectif"}],
        [{"text": "💰 Modifier Mise"}, {"text": "⏱️ Durée Trade"}],
        [{"text": "🔄 Restart"}, {"text": "🎮 Mode"}],
        [{"text": "📤 Exporter CSV"}, {"text": "Changer Actif (manuel)"}],
        [{"text": "📊 Voir liste noire"}, {"text": "🧠 Voir Cerveau IA"}], # <--- LE NOUVEAU BOUTON EST ICI
        [{"text": "🗑️ Effacer Mémoire (JSON)"}]
    ]
    
    if CONFIG["paused"]:
        keyboard.append([{"text": "▶️ Reprendre"}, {"text": "⏹ Stop & Reset"}])
    else:
        keyboard.append([{"text": "⏸ Pause"}])
    
    return {"keyboard": keyboard, "resize_keyboard": True}

def multi_assets_sub_keyboard():
    status = "🟢 ON" if CONFIG.get("multi_assets_enabled", False) else "🔴 OFF"
    filtre = CONFIG.get("asset_filter", "OTC") # Filtre par défaut
    return {
        "keyboard": [
            [{"text": f"Activer Multi-Actifs : {status}"}],
            [{"text": f"Filtre Actuel : {filtre}"}],
            [{"text": "🔄 Filtrer : OTC"}, {"text": "🔄 Filtrer : CRYPTO"}],
            [{"text": "🔄 Filtrer : FOREX"}, {"text": "🔄 Filtrer : TOUT"}],
            [{"text": "🏠 Retour Menu"}]
        ],
        "resize_keyboard": True
    }

def mode_sub_keyboard():
    m_actuel = MODES_CONFIG[CONFIG.get("mode", 1)]["nom"]
    return {
        "keyboard": [
            [{"text": f"Mode Actuel : {m_actuel}"}],
            [{"text": "🕹 Mode : REEL"}, {"text": "🕹 Mode : DEMO"}],
            [{"text": "🕹 Mode : TOURNOI"}, {"text": "🏠 Retour Menu"}]
        ],
        "resize_keyboard": True
    }

def report_sub_keyboard():
    keyboard = [[{"text": f"Rapport {actif}"}] for actif in CONFIG["preferred_actifs"]]
    keyboard.append([{"text": "Rapport Global"}])
    keyboard.append([{"text": "🏠 Retour Menu"}])
    return {"keyboard": keyboard, "resize_keyboard": True}

def ema_filter_sub_keyboard():
    status = "🟢 ON" if CONFIG.get("use_ema_filter", False) else "🔴 OFF"
    return {
        "keyboard": [
            [{"text": f"EMA Filter ON/OFF ({status})"}],
            [{"text": "Régler Période EMA"}],
            [{"text": "🏠 Retour Menu"}]
        ],
        "resize_keyboard": True
    }

def rsi_filter_sub_keyboard():
    status = "🟢 ON" if CONFIG.get("use_rsi_filter", False) else "🔴 OFF"
    return {
        "keyboard": [
            [{"text": f"RSI Filter ON/OFF ({status})"}],
            [{"text": "Régler Période RSI"}],
            [{"text": "🏠 Retour Menu"}]
        ],
        "resize_keyboard": True
    }

def limit_profit_sub_keyboard():
    dd = CONFIG.get("max_drawdown_target_pct", -10.0)
    profit = CONFIG.get("max_profit_target_pct", 20.0)
    payout = CONFIG.get("min_payout", 91) # On récupère le paramètre
    return {
        "keyboard": [
            [{"text": f"Limite DD (drawdown max) : {dd:.1f}%"}],
            [{"text": f"Limite Profit (gain max) : {profit:.1f}%"}],
            [{"text": f"⚙️ Min Payout : {payout}%"}],
            [{"text": "🏠 Retour Menu"}]
        ],
        "resize_keyboard": True
    }

def strategy_keyboard():
    from config import CONFIG
    
    # La liste complète de tes 11 stratégies
    all_strategies = [
        "Pin Bar", "Engulfing", 
        "Breakout", "Three Line Strike", 
        "Pin Bar + EMA Filter", "Rejection Wick", 
        "EMA Cross + RSI", "Railroad Tracks", 
        "BB Squeeze Break", "Cassure", 
        "Order Block"
    ]
    
    keyboard = []
    row = []
    
    # Construction dynamique des boutons sur 2 colonnes
    for strat in all_strategies:
        statut = "✅" if strat in CONFIG.get("active_strategies", []) else "❌"
        row.append({"text": f"{statut} {strat}"})
        
        if len(row) == 2:
            keyboard.append(row)
            row = []
            
    # Si le nombre de stratégies est impair, on ajoute le bouton restant sur sa propre ligne
    if row:
        keyboard.append(row)
        
    # On ajoute toujours le bouton de retour à la fin
    keyboard.append([{"text": "🏠 Retour Menu"}])
    
    return {"keyboard": keyboard, "resize_keyboard": True}

def get_report_text(actif=None):
    import time
    uptime_sec = int(time.time() - STATS["start_time"])
    hours = uptime_sec // 3600
    minutes = (uptime_sec % 3600) // 60
    seconds = uptime_sec % 60
    
    mode_nom = MODES_CONFIG[CONFIG["mode"]]["nom"]
    status = "⏸ EN PAUSE" if CONFIG["paused"] else "🏃 EN COURS"
    
    profit = STATS["current_balance"] - STATS["start_balance"]
    profit_pct = (profit / STATS["start_balance"] * 100) if STATS["start_balance"] > 0 else 0.0
    
    streak_text = f"🔥 {STATS['win_streak']} wins d’affilée" if STATS["win_streak"] > 0 else f"❄️ {STATS['loss_streak']} pertes d’affilée"
    first_trade_str = time.strftime("%H:%M:%S", time.localtime(STATS["first_trade_time"])) if STATS["first_trade_time"] > 0 else "Aucun"
    last_trade_str = time.strftime("%H:%M:%S", time.localtime(STATS["last_trade_time"])) if STATS["last_trade_time"] > 0 else "Aucun"
    
    alerts = []
    if STATS["max_drawdown_pct"] > 10:
        alerts.append("⚠️ Drawdown élevé (>10%) - Réduisez les risques")

    if actif:
        asset_stat = STATS["assets"].get(actif, {"wins": 0, "losses": 0, "total_gross_profit": 0.0, "total_gross_loss": 0.0, "strategy_stats": {}})
        wins = asset_stat["wins"]
        losses = asset_stat["losses"]
        total_trades = wins + losses
        winrate = (wins / total_trades * 100) if total_trades > 0 else 0.0
        profit_factor = (asset_stat["total_gross_profit"] / abs(asset_stat["total_gross_loss"])) if asset_stat["total_gross_loss"] != 0 else 0.0
        avg_win = (asset_stat["total_gross_profit"] / wins) if wins > 0 else 0.0
        avg_loss = (asset_stat["total_gross_loss"] / losses) if losses > 0 else 0.0
        risk_reward = avg_win / abs(avg_loss) if avg_loss != 0 else 0.0
        
        max_w = asset_stat.get("max_win", 0.0)
        max_l = asset_stat.get("max_loss", 0.0)
        max_s = asset_stat.get("max_stake", 0.0)

        sorted_strats = sorted(asset_stat.get("strategy_stats", {}).items(), key=lambda x: x[1]["profit"], reverse=True)
        report_title = f"📊 RAPPORT POUR {actif.upper()}"

    else:
        wins = STATS["wins"]
        losses = STATS["losses"]
        total_trades = wins + losses
        winrate = (wins / total_trades * 100) if total_trades > 0 else 0.0
        profit_factor = (STATS["total_gross_profit"] / abs(STATS["total_gross_loss"])) if STATS["total_gross_loss"] != 0 else 0.0
        avg_win = (STATS["total_gross_profit"] / wins) if wins > 0 else 0.0
        avg_loss = (STATS["total_gross_loss"] / losses) if losses > 0 else 0.0
        risk_reward = avg_win / abs(avg_loss) if avg_loss != 0 else 0.0
        
        max_w = STATS.get("max_win", 0.0)
        max_l = STATS.get("max_loss", 0.0)
        max_s = STATS.get("max_stake", 0.0)

        sorted_strats = sorted(STATS.get("strategy_stats", {}).items(), key=lambda x: x[1]["profit"], reverse=True)
        report_title = "📊 RAPPORT GLOBAL"

    if total_trades > 0 and winrate < 50:
        alerts.append("📉 Winrate faible - Revoyez les strats")
    alerts_text = "\n".join(alerts) if alerts else "✅ Tout va bien"

    strat_text = ""
    if sorted_strats:
        best_strat = sorted_strats[0][0]
        worst_strat = sorted_strats[-1][0]
        for s, data in sorted_strats:
            s_trades = data["wins"] + data["losses"]
            s_winrate = (data["wins"] / s_trades * 100) if s_trades > 0 else 0.0
            emoji = "🟢" if data["profit"] >= 0 else "🔴"
            strat_text += f"{emoji} <b>{s}</b>\n   Trades {s_trades} | WR {s_winrate:.1f}% | PnL {data['profit']:+.2f}$\n"
        strat_text += f"\n🏆 Meilleure : <b>{best_strat}</b>\n⚠️ Pire : <b>{worst_strat}</b>\n"
    else:
        strat_text = "Aucune donnée stratégie\n"

    return (
        f"{report_title}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🤖 Bot     : JHBot PRO v2.0\n"
        f"🌍 Mode    : <b>{mode_nom}</b>\n"
        f"📍 Actif   : <b>{CONFIG['actif']}</b>\n"
        f"⏱️ Uptime  : {hours}h {minutes:02d}m {seconds:02d}s\n"
        f"📍 Statut  : {status}\n\n"
        
        f"💰 <b>SOLDE & PROFIT</b>\n"
        f"Initial   : {STATS['start_balance']:.2f}$\n"
        f"Actuel    : <b>{STATS['current_balance']:.2f}$</b>\n"
        f"Profit    : <b>{profit:+.2f}$</b>  (<b>{profit_pct:+.1f}%</b>)\n"
        f"Max DD    : <b>-{STATS['max_drawdown']:.2f}$</b>  (<b>-{STATS['max_drawdown_pct']:.1f}%</b>)\n\n"
        
        f"📈 <b>PERFORMANCE</b>\n"
        f"✅ Wins     : {wins}\n"
        f"❌ Losses   : {losses}\n"
        f"🎯 Winrate  : <b>{winrate:.1f}%</b>\n"
        f"🔢 Total    : {total_trades} trades\n\n"
        
        f"⚙️ <b>RISK & RECORDS</b>\n"
        f"Mise actuelle   : <b>{CONFIG['montant_actuel']:.2f}$</b>\n"
        f"Plus grosse mise: <b>{max_s:.2f}$</b>\n"
        f"Plus gros gain  : <b>+{max_w:.2f}$</b>\n"
        f"Plus grosse perte: <b>{max_l:.2f}$</b>\n"
        f"Profit Factor   : <b>{profit_factor:.2f}</b>\n\n"
        
        f"🏆 <b>PAR STRATÉGIE</b>\n"
        f"{strat_text}\n"
        
        f"📉 <b>INDICATEURS</b>\n"
        f"EMA         : {STATS['ema_val']:.5f}\n"
        f"RSI {CONFIG['rsi_period']}     : <b>{STATS['rsi_val']:.1f}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    )

def timeframe_sub_keyboard():
    from config import CONFIG
    actuel = CONFIG.get("duree", 5)
    
    if actuel == 60: text_actuel = "1 Minute"
    elif actuel == 300: text_actuel = "5 Minutes"
    else: text_actuel = f"{actuel} Secondes"

    return {
        "keyboard": [
            [{"text": f"⏳ Actuel : {text_actuel}"}],
            [{"text": "⚡ 5 Secondes"}, {"text": "🐇 15 Secondes"}],
            [{"text": "🚶 1 Minute"}, {"text": "🐢 5 Minutes"}],
            [{"text": "🏠 Retour Menu"}]
        ],
        "resize_keyboard": True
    }