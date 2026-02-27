from config import STATS, CONFIG

class SuperStrategy:
    def __init__(self):
        self.prices = []
        self.gains = []
        self.losses = []
        self.candles = []
        
        self.ema1, self.prev_ema1 = 0.0, 0.0
        self.ema5, self.prev_ema5 = 0.0, 0.0
        self.ema11, self.prev_ema11 = 0.0, 0.0
        self.ema50 = 0.0
        self.ema50_history = [] # Pour détecter la tendance
        
        self.bb_upper, self.bb_middle, self.bb_lower = 0, 0, 0
        self.bb_widths = []

    def warm_up(self, history_candles):
        print(f"📥 Préchauffage ({len(history_candles)} bougies) - Moteur IA activé...")
        self.prices = []
        self.candles = []
        self.bb_widths = []
        self.ema50_history = []
        for candle in history_candles:
            close_p = float(candle.get('close') or candle.get('c', 0))
            open_p = float(candle.get('open') or candle.get('o', 0))
            high_p = float(candle.get('high') or candle.get('h', 0))
            low_p = float(candle.get('low') or candle.get('l', 0))
            self.update_indicators(close_p)
            self.candles.append({'o': open_p, 'h': high_p, 'l': low_p, 'c': close_p})
            if len(self.candles) > 40: self.candles.pop(0)

    def update_indicators(self, price):
        price = float(price)
        self.prices.append(price)
        if len(self.prices) > 120: self.prices.pop(0)
        
        # --- CALCULS EMA DE BASE ---
        alpha1 = 2 / (1 + 1)
        self.ema1 = price if self.ema1 == 0 else (price - self.ema1) * alpha1 + self.ema1
        self.prev_ema1 = self.ema1

        self.prev_ema5, self.prev_ema11 = self.ema5, self.ema11
        alpha5, alpha11 = 2/6, 2/12
        self.ema5 = price if self.ema5 == 0 else (price - self.ema5) * alpha5 + self.ema5
        self.ema11 = price if self.ema11 == 0 else (price - self.ema11) * alpha11 + self.ema11

        alpha50 = 2 / (50 + 1)
        self.ema50 = price if self.ema50 == 0 else (price - self.ema50) * alpha50 + self.ema50
        
        # Historique EMA50 pour détecter la pente du marché
        self.ema50_history.append(self.ema50)
        if len(self.ema50_history) > 25: self.ema50_history.pop(0)

        # --- EMA DYNAMIQUE (Telegram) ---
        ema_p = CONFIG.get("ema_period", 14)
        alpha_custom = 2 / (ema_p + 1)
        if STATS.get("ema_val", 0) == 0: 
            STATS["ema_val"] = price
        else: 
            STATS["ema_val"] = (price - STATS.get("ema_val", price)) * alpha_custom + STATS.get("ema_val", price)

        # --- RSI DYNAMIQUE (Telegram) ---
        rsi_p = CONFIG.get("rsi_period", 14)
        if len(self.prices) > 1:
            diff = self.prices[-1] - self.prices[-2]
            self.gains.append(max(diff, 0))
            self.losses.append(abs(min(diff, 0)))
            
            # Auto-adaptation si l'utilisateur réduit la période du RSI en plein trade
            while len(self.gains) > rsi_p:
                self.gains.pop(0)
                self.losses.pop(0)
                
            if len(self.gains) == rsi_p:
                avg_g = sum(self.gains) / rsi_p
                avg_l = sum(self.losses) / rsi_p
                rs = avg_g / avg_l if avg_l != 0 else 100
                STATS["rsi_val"] = 100 - (100 / (1 + rs))

        # --- BANDES DE BOLLINGER ---
        if len(self.prices) >= 20:
            sma = sum(self.prices[-20:]) / 20
            variance = sum((p - sma)**2 for p in self.prices[-20:]) / 20
            std = variance ** 0.5
            self.bb_upper, self.bb_middle, self.bb_lower = sma + 2 * std, sma, sma - 2 * std
            
            self.bb_widths.append(self.bb_upper - self.bb_lower)
            if len(self.bb_widths) > 25: self.bb_widths.pop(0)

        return STATS.get("ema_val", price)

    def get_market_regime(self):
        """ Le Cerveau : Détecte l'état actuel du marché """
        if len(self.ema50_history) < 20 or len(self.candles) < 20:
            return "RANGE"
        
        old_ema = self.ema50_history[-20]
        current_ema = self.ema50_history[-1]
        
        # Volatilité moyenne (mini ATR sur 20 bougies)
        highs = [c['h'] for c in self.candles[-20:]]
        lows = [c['l'] for c in self.candles[-20:]]
        avg_candle_size = sum(h - l for h, l in zip(highs, lows)) / 20
        
        slope = current_ema - old_ema
        
        # Si la moyenne mobile monte très fort par rapport à la taille des bougies = TENDANCE HAUSSIÈRE
        if slope > avg_candle_size * 0.4:
            return "TREND_UP"
        # Si elle chute fort = TENDANCE BAISSIÈRE
        elif slope < -avg_candle_size * 0.4:
            return "TREND_DOWN"
        else:
            return "RANGE"

    def check_patterns(self, c1, c2):
        active = CONFIG.get("active_strategies", [])
        price = c2['c']
        regime = self.get_market_regime()
        
        # --- FILTRES DYNAMIQUES UTILISATEUR ---
        use_rsi = CONFIG.get("use_rsi_filter", False)
        current_rsi = STATS.get("rsi_val", 50)

        def validate_signal(direction, name):
            """ Le Juge : Valide ou rejette le signal selon le marché """
            # 1. Protection Anti-Contre-Tendance bête
            if regime == "TREND_UP" and direction == "put" and name not in ["Rejection Wick", "Pin Bar"]:
                return None
            if regime == "TREND_DOWN" and direction == "call" and name not in ["Rejection Wick", "Pin Bar"]:
                return None
            
            # 2. Protection Anti-Breakout en marché plat
            if regime == "RANGE" and name in ["Breakout", "Three Line Strike"]:
                return None
                
            # 3. Filtre RSI Global de l'utilisateur
            if use_rsi:
                if direction == "call" and current_rsi > 70: return None 
                if direction == "put" and current_rsi < 30: return None  

            # ---> NOUVEAUTÉ 4. Le Filtre d'Auto-Désactivation <---
            if name in STATS.get("banned_strats", []):
                return None # La stratégie a été bannie pour mauvaise performance
                
            return (direction, name)

        # --- DÉTECTION DES STRATÉGIES ---
        
        # =========================================================
        # 1. STRATÉGIE "PIN BAR" (Version Pro / Sniper)
        # =========================================================
        if "Pin Bar" in active:
            body2 = abs(c2['c'] - c2['o'])
            total_length2 = c2['h'] - c2['l']
            
            # Éviter la division par zéro
            if total_length2 > 0:
                # Les min/max permettent d'ignorer complètement la couleur de la bougie
                upper_wick2 = c2['h'] - max(c2['o'], c2['c'])
                lower_wick2 = min(c2['o'], c2['c']) - c2['l']
                
                bb_up = getattr(self, 'bb_upper', 0)
                bb_low = getattr(self, 'bb_lower', 0)

                # --- RECHERCHE DE PIN BAR HAUSSIER (Marteau / Call) ---
                # Règle 1 : Mèche basse > 60%, Corps < 30%. (Laisse 10% pour une petite mèche haute)
                # La couleur de CE pin bar n'a pas d'importance.
                if lower_wick2 >= (total_length2 * 0.60) and body2 <= (total_length2 * 0.30):
                    # Règle 2 : Le marché précédent devait baisser
                    if c1['c'] < c1['o']:
                        # Règle 3 : Rejet sur le bas des Bandes de Bollinger
                        if bb_low == 0 or c2['l'] <= (bb_low * 1.0005): 
                            res = validate_signal("call", "Pin Bar")
                            if res: return res

                # --- RECHERCHE DE PIN BAR BAISSIER (Étoile Filante / Put) ---
                # Règle 1 : Mèche haute > 60%, Corps < 30%. (Laisse 10% pour une petite mèche basse)
                # La couleur de CE pin bar n'a pas d'importance.
                if upper_wick2 >= (total_length2 * 0.60) and body2 <= (total_length2 * 0.30):
                    # Règle 2 : Le marché précédent devait monter
                    if c1['c'] > c1['o']:
                        # Règle 3 : Rejet sur le haut des Bandes de Bollinger
                        if bb_up == 0 or c2['h'] >= (bb_up * 0.9995):
                            res = validate_signal("put", "Pin Bar")
                            if res: return res

        # =========================================================
        # 2. STRATÉGIE "ENGULFING" (Version Pro / Momentum)
        # =========================================================
        if "Engulfing" in active:
            body1 = abs(c1['c'] - c1['o'])
            body2 = abs(c2['c'] - c2['o'])
            
            # On récupère les indicateurs pour le filtrage de zone
            rsi = STATS.get("rsi_val", 50)
            bb_low = getattr(self, 'bb_lower', 0)
            bb_up = getattr(self, 'bb_upper', 0)

            # --- AVALEMENT HAUSSIER (Bullish Engulfing) ---
            # 1. La bougie 1 est rouge, la bougie 2 est verte
            if c1['c'] < c1['o'] and c2['c'] > c2['o']:
                # 2. Le corps 2 avale totalement le corps 1
                if c2['c'] >= c1['o'] and c2['o'] <= c1['c']:
                    # 3. FILTRE PUISSANCE : Le corps 2 est au moins 1.2x plus grand que le corps 1
                    # 4. FILTRE ÉPUISEMENT : On évite les bougies démesurées (ex: corps2 > 3x corps1)
                    if body2 >= (body1 * 1.2) and body2 <= (body1 * 4.0):
                        # 5. FILTRE DE ZONE : Soit RSI bas (< 40), soit on touche la BB basse
                        if rsi < 40 or (bb_low > 0 and c2['l'] <= bb_low * 1.0005):
                            res = validate_signal("call", "Engulfing")
                            if res: return res

            # --- AVALEMENT BAISSIER (Bearish Engulfing) ---
            # 1. La bougie 1 est verte, la bougie 2 est rouge
            if c1['c'] > c1['o'] and c2['c'] < c2['o']:
                # 2. Le corps 2 avale totalement le corps 1
                if c2['c'] <= c1['o'] and c2['o'] >= c1['c']:
                    # 3. FILTRE PUISSANCE
                    if body2 >= (body1 * 1.2) and body2 <= (body1 * 4.0):
                        # 4. FILTRE DE ZONE : Soit RSI haut (> 60), soit on touche la BB haute
                        if rsi > 60 or (bb_up > 0 and c2['h'] >= bb_up * 0.9995):
                            res = validate_signal("put", "Engulfing")
                            if res: return res

        # =========================================================
        # 3. STRATÉGIE "BREAKOUT" (Version Pro / Squeeze)
        # =========================================================
        if "Breakout" in active and len(self.candles) >= 22:
            # 1. On définit la zone de consolidation (Range) sur les 20 dernières bougies
            # On exclut la bougie actuelle (c2) du calcul
            recent_high = max([x['h'] for x in self.candles[-21:-1]])
            recent_low = min([x['l'] for x in self.candles[-21:-1]])
            
            # 2. Calcul de la force de la cassure
            body2 = abs(c2['c'] - c2['o'])
            avg_body = sum([abs(x['c'] - x['o']) for x in self.candles[-11:-1]]) / 10
            
            # 3. Récupération des filtres
            ema50 = getattr(self, 'ema50', 0)
            rsi = STATS.get("rsi_val", 50)
            
            # --- BREAKOUT HAUSSIER (Call) ---
            # Règle A : La bougie clôture au-dessus du plus haut récent
            if c2['c'] > recent_high and c2['o'] <= recent_high:
                # Règle B : Momentum - La bougie doit être plus grande que la moyenne (volatilité)
                # Règle C : Pas de mèche supérieure trop grande (rejet)
                upper_wick2 = c2['h'] - c2['c']
                if body2 > avg_body and upper_wick2 < (body2 * 0.3):
                    # Règle D : Tendance - On est au-dessus de l'EMA 50 et RSI pas encore en surachat
                    if (ema50 == 0 or c2['c'] > ema50) and rsi < 65:
                        res = validate_signal("call", "Breakout")
                        if res: return res

            # --- BREAKOUT BAISSIER (Put) ---
            # Règle A : La bougie clôture sous le plus bas récent
            if c2['c'] < recent_low and c2['o'] >= recent_low:
                # Règle B : Momentum
                lower_wick2 = c2['c'] - c2['l']
                if body2 > avg_body and lower_wick2 < (body2 * 0.3):
                    # Règle D : Tendance - On est sous l'EMA 50 et RSI pas encore en survente
                    if (ema50 == 0 or c2['c'] < ema50) and rsi > 35:
                        res = validate_signal("put", "Breakout")
                        if res: return res

        # =========================================================
        # 4. STRATÉGIE "THREE LINE STRIKE" (Version Pro / Continuation)
        # =========================================================
        if "Three Line Strike" in active and len(self.candles) >= 5:
            # On récupère les 4 bougies de la séquence
            # c2 est l'actuelle (la bougie de frappe), c1, c0 et cm1 sont les 3 précédentes
            c2 = self.candles[-1]
            c1 = self.candles[-2]
            c0 = self.candles[-3]
            cm1 = self.candles[-4]
            
            ema50 = getattr(self, 'ema50', 0)
            rsi = STATS.get("rsi_val", 50)

            # --- THREE LINE STRIKE HAUSSIER (Bullish - Signal de CALL) ---
            # 1. Trois bougies descendantes (rouges)
            if cm1['c'] < cm1['o'] and c0['c'] < c0['o'] and c1['c'] < c1['o']:
                # 2. Chaque bougie clôture plus bas que la précédente (escalier)
                if c1['c'] < c0['c'] < cm1['c']:
                    # 3. La 4ème bougie (c2) est verte et avale l'ouverture de la 1ère (cm1)
                    if c2['c'] > c2['o'] and c2['c'] > cm1['o'] and c2['o'] <= c1['c']:
                        # 4. FILTRE DE TENDANCE : On ne valide que si la tendance de fond est haussière
                        if (ema50 == 0 or c2['c'] > ema50) and rsi < 70:
                            res = validate_signal("call", "Three Line Strike")
                            if res: return res

            # --- THREE LINE STRIKE BAISSIER (Bearish - Signal de PUT) ---
            # 1. Trois bougies ascendantes (vertes)
            if cm1['c'] > cm1['o'] and c0['c'] > c0['o'] and c1['c'] > c1['o']:
                # 2. Chaque bougie clôture plus haut que la précédente
                if c1['c'] > c0['c'] > cm1['c']:
                    # 3. La 4ème bougie (c2) est rouge et avale l'ouverture de la 1ère (cm1)
                    if c2['c'] < c2['o'] and c2['c'] < cm1['o'] and c2['o'] >= c1['c']:
                        # 4. FILTRE DE TENDANCE
                        if (ema50 == 0 or c2['c'] < ema50) and rsi > 30:
                            res = validate_signal("put", "Three Line Strike")
                            if res: return res

        # =========================================================
        # 5. PIN BAR + EMA FILTER (Version Pro / Trend-Following)
        # =========================================================
        if "Pin Bar + EMA Filter" in active:
            body2 = abs(c2['c'] - c2['o'])
            total_length2 = c2['h'] - c2['l']
            
            if total_length2 > 0:
                upper_wick2 = c2['h'] - max(c2['o'], c2['c'])
                lower_wick2 = min(c2['o'], c2['c']) - c2['l']
                
                # Utilisation des EMA pour le filtrage
                ema_med = self.ema5  # EMA 14 (Support/Résistance dynamique)
                ema_trend = self.ema50 # EMA 50 (Tendance de fond)

                # --- SIGNAL CALL (Achat en Tendance Haussière) ---
                # 1. Tendance confirmée : Prix au-dessus de l'EMA 50
                if ema_trend > 0 and c2['c'] > ema_trend:
                    # 2. Forme Pin Bar (Mèche basse > 60%, Petit corps < 30%)
                    if lower_wick2 >= (total_length2 * 0.60) and body2 <= (total_length2 * 0.30):
                        # 3. LE REBOND : La mèche basse doit avoir "piqué" l'EMA 14
                        # On vérifie que le point bas est sous l'EMA 14 mais que la clôture est au-dessus
                        if c2['l'] <= ema_med and c2['c'] > (ema_med * 0.9998):
                            res = validate_signal("call", "Pin Bar + EMA Filter")
                            if res: return res

                # --- SIGNAL PUT (Vente en Tendance Baissière) ---
                # 1. Tendance confirmée : Prix sous l'EMA 50
                if ema_trend > 0 and c2['c'] < ema_trend:
                    # 2. Forme Pin Bar (Mèche haute > 60%, Petit corps < 30%)
                    if upper_wick2 >= (total_length2 * 0.60) and body2 <= (total_length2 * 0.30):
                        # 3. LE REBOND : La mèche haute doit avoir "piqué" l'EMA 14
                        # On vérifie que le point haut est au-dessus de l'EMA 14 mais que la clôture est dessous
                        if c2['h'] >= ema_med and c2['c'] < (ema_med * 1.0002):
                            res = validate_signal("put", "Pin Bar + EMA Filter")
                            if res: return res

        # =========================================================
        # 6. STRATÉGIE "REJECTION WICK" (Version Pro / Exhaustion)
        # =========================================================
        if "Rejection Wick" in active and len(self.candles) >= 6:
            body2 = abs(c2['c'] - c2['o'])
            total_length2 = c2['h'] - c2['l']
            
            if total_length2 > 0:
                upper_wick2 = c2['h'] - max(c2['o'], c2['c'])
                lower_wick2 = min(c2['o'], c2['c']) - c2['l']
                
                # On calcule la mèche maximale des 5 bougies précédentes pour comparer
                max_prev_upper = max([x['h'] - max(x['o'], x['c']) for x in self.candles[-6:-1]])
                max_prev_lower = max([min(x['o'], x['c']) - x['l'] for x in self.candles[-6:-1]])
                
                bb_up = getattr(self, 'bb_upper', 0)
                bb_low = getattr(self, 'bb_lower', 0)
                rsi = STATS.get("rsi_val", 50)

                # --- REJET HAUSSIER (Call) ---
                # 1. Mèche basse dominante (au moins 2.5x le corps)
                if lower_wick2 > (body2 * 2.5) and lower_wick2 > max_prev_lower:
                    # 2. Zone de sur-vente RSI + Rejet Bande de Bollinger basse
                    if rsi < 35 and (bb_low > 0 and c2['l'] <= bb_low):
                        res = validate_signal("call", "Rejection Wick")
                        if res: return res

                # --- REJET BAISSIER (Put) ---
                # 1. Mèche haute dominante (au moins 2.5x le corps)
                if upper_wick2 > (body2 * 2.5) and upper_wick2 > max_prev_upper:
                    # 2. Zone de sur-achat RSI + Rejet Bande de Bollinger haute
                    if rsi > 65 and (bb_up > 0 and c2['h'] >= bb_up):
                        res = validate_signal("put", "Rejection Wick")
                        if res: return res

        # =========================================================
        # 7. EMA CROSS + RSI (Version Pro / Trend Follower)
        # =========================================================
        if "EMA Cross + RSI" in active:
            # On utilise les EMA calculées dans update_indicators
            # ema1 = rapide (ex: 7), ema5 = moyenne (ex: 14), ema50 = tendance
            fast = self.ema1
            slow = self.ema5
            prev_fast = self.prev_ema1
            prev_slow = self.prev_ema5
            
            rsi = STATS.get("rsi_val", 50)
            ema50 = getattr(self, 'ema50', 0)

            # --- SIGNAL DE CROISEMENT HAUSSIER (Call) ---
            # 1. Le croisement vient de se produire (Rapide passe au-dessus de Lente)
            if fast > slow and prev_fast <= prev_slow:
                # 2. Le RSI confirme la poussée (Momentum positif)
                # On veut que le RSI soit entre 52 et 65 (début de poussée saine)
                if 52 <= rsi <= 68:
                    # 3. Validation par la tendance de fond (EMA 50)
                    if ema50 == 0 or c2['c'] > ema50:
                        res = validate_signal("call", "EMA Cross + RSI")
                        if res: return res

            # --- SIGNAL DE CROISEMENT BAISSIER (Put) ---
            # 1. Le croisement vient de se produire (Rapide passe sous Lente)
            if fast < slow and prev_fast >= prev_slow:
                # 2. Le RSI confirme la chute (Momentum négatif)
                # On veut que le RSI soit entre 32 et 48
                if 32 <= rsi <= 48:
                    # 3. Validation par la tendance de fond
                    if ema50 == 0 or c2['c'] < ema50:
                        res = validate_signal("put", "EMA Cross + RSI")
                        if res: return res

        # =========================================================
        # 8. STRATÉGIE "RAILROAD TRACKS" (Version Pro / Reversal)
        # =========================================================
        if "Railroad Tracks" in active:
            body1 = abs(c1['c'] - c1['o'])
            body2 = abs(c2['c'] - c2['o'])
            
            # Calcul de la moyenne des corps récents pour filtrer le "bruit"
            avg_body = sum([abs(x['c'] - x['o']) for x in self.candles[-6:-1]]) / 5
            
            bb_low = getattr(self, 'bb_lower', 0)
            bb_up = getattr(self, 'bb_upper', 0)

            # --- RAILROAD TRACKS HAUSSIER (Call) ---
            # 1. Bougie 1 rouge, Bougie 2 verte
            if c1['c'] < c1['o'] and c2['c'] > c2['o']:
                # 2. Les deux bougies font environ la même taille (80% à 120%)
                if body1 > 0 and (0.8 <= (body2 / body1) <= 1.2):
                    # 3. Les bougies sont significatives (plus grandes que la moyenne)
                    if body2 > avg_body:
                        # 4. Alignement des bas (les "rails")
                        diff_low = abs(c1['l'] - c2['l'])
                        if diff_low < (body2 * 0.1): # Tolérance de 10% du corps
                            # 5. Zone de rejet : Rebond sur BB basse
                            if bb_low == 0 or c2['l'] <= bb_low * 1.0005:
                                res = validate_signal("call", "Railroad Tracks")
                                if res: return res

            # --- RAILROAD TRACKS BAISSIER (Put) ---
            # 1. Bougie 1 verte, Bougie 2 rouge
            if c1['c'] > c1['o'] and c2['c'] < c2['o']:
                # 2. Symétrie des corps
                if body1 > 0 and (0.8 <= (body2 / body1) <= 1.2):
                    # 3. Taille significative
                    if body2 > avg_body:
                        # 4. Alignement des hauts
                        diff_high = abs(c1['h'] - c2['h'])
                        if diff_high < (body2 * 0.1):
                            # 5. Zone de rejet : Rebond sur BB haute
                            if bb_up == 0 or c2['h'] >= bb_up * 0.9995:
                                res = validate_signal("put", "Railroad Tracks")
                                if res: return res

        # =========================================================
        # 9. BB SQUEEZE BREAK (Version Pro / Explosive)
        # =========================================================
        if "BB Squeeze Break" in active and len(self.bb_widths) >= 21:
            # 1. On calcule la largeur moyenne des bandes sur 20 bougies
            avg_width = sum(self.bb_widths[-21:-1]) / 20
            current_width = self.bb_widths[-1]
            
            # 2. Détection du Squeeze : les bandes sont 10% plus serrées que d'habitude
            is_squeezed = current_width < (avg_width * 0.90)
            
            # 3. Calcul de la force de la bougie actuelle
            body2 = abs(c2['c'] - c2['o'])
            avg_body = sum([abs(x['c'] - x['o']) for x in self.candles[-11:-1]]) / 10
            
            rsi = STATS.get("rsi_val", 50)
            ema50 = getattr(self, 'ema50', 0)
            bb_up = getattr(self, 'bb_upper', 0)
            bb_low = getattr(self, 'bb_lower', 0)

            # --- CASSURE HAUSSIÈRE (Call) ---
            # On vient d'un squeeze ET la bougie clôture au-dessus de la BB haute
            if is_squeezed and c2['c'] > bb_up and bb_up > 0:
                # Validation par le corps (bougie de décision) et la tendance
                if body2 > avg_body and rsi > 50:
                    if ema50 == 0 or c2['c'] > ema50:
                        res = validate_signal("call", "BB Squeeze Break")
                        if res: return res

            # --- CASSURE BAISSIÈRE (Put) ---
            # On vient d'un squeeze ET la bougie clôture sous la BB basse
            if is_squeezed and c2['c'] < bb_low and bb_low > 0:
                # Validation par le corps et la tendance
                if body2 > avg_body and rsi < 50:
                    if ema50 == 0 or c2['c'] < ema50:
                        res = validate_signal("put", "BB Squeeze Break")
                        if res: return res

        # 10. Stratégie de Cassure (Vrai Support / Résistance)
        if "Cassure" in active and len(self.candles) >= 15:
            # On cherche les plus hauts et plus bas majeurs sur 14 bougies
            recent_high = max([x['h'] for x in self.candles[-15:-1]])
            recent_low = min([x['l'] for x in self.candles[-15:-1]])
            
            body = abs(c2['c'] - c2['o'])
            range_total = recent_high - recent_low
            
            if range_total > price * 0.00005: # S'assurer qu'on n'est pas dans un micro-range plat
                # Cassure Résistance (à la hausse)
                if c2['c'] > recent_high and c2['o'] < recent_high and body > range_total * 0.2:
                    res = validate_signal("call", "Cassure")
                    if res: return res
                
                # Cassure Support (à la baisse)
                if c2['c'] < recent_low and c2['o'] > recent_low and body > range_total * 0.2:
                    res = validate_signal("put", "Cassure")
                    if res: return res

        # 11. Stratégie Order Block (Smart Money Concepts)
        if "Order Block" in active and len(self.candles) >= 12:
            # On scanne le passé récent pour trouver une forte impulsion
            for i in range(3, 11):
                ob_candle = self.candles[-(i+2)]
                impulse1 = self.candles[-(i+1)]
                impulse2 = self.candles[-i]
                
                # RECHERCHE ORDER BLOCK HAUSSIER (Dernière rouge avant forte hausse)
                if ob_candle['c'] < ob_candle['o'] and impulse1['c'] > impulse1['o'] and impulse2['c'] > impulse2['o']:
                    # Vérifier que l'impulsion est vraiment forte
                    if (impulse2['c'] - impulse1['o']) > (ob_candle['h'] - ob_candle['l']) * 1.5:
                        ob_high = ob_candle['h']
                        ob_low = ob_candle['l']
                        
                        # Si le prix actuel vient de retomber dans la zone de l'OB
                        if c2['l'] <= ob_high and c2['o'] > ob_high:
                            res = validate_signal("call", "Order Block")
                            if res: return res

                # RECHERCHE ORDER BLOCK BAISSIER (Dernière verte avant forte baisse)
                if ob_candle['c'] > ob_candle['o'] and impulse1['c'] < impulse1['o'] and impulse2['c'] < impulse2['o']:
                    # Vérifier que l'impulsion est vraiment forte
                    if (impulse1['o'] - impulse2['c']) > (ob_candle['h'] - ob_candle['l']) * 1.5:
                        ob_high = ob_candle['h']
                        ob_low = ob_candle['l']
                        
                        # Si le prix actuel vient de remonter dans la zone de l'OB
                        if c2['h'] >= ob_low and c2['o'] < ob_low:
                            res = validate_signal("put", "Order Block")
                            if res: return res
        return None