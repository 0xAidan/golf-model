"""
Backtest v4.2 fixes against Cognizant Classic — CLEAN DATA ONLY.

Key differences from v4.1 backtest:
  1. Uses ONLY pre-tournament odds (Feb 26 timestamp, not Feb 28 in-play)
  2. Filters DG probs to confirmed field (removes 66 phantom players)
  3. Renormalizes DG probs after phantom removal
  4. Compares v4.2 (clean) vs v4.1 (contaminated) vs v4.0 (original)
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.db import get_conn
from src import config
from src.portfolio import enforce_diversification

TOURNAMENT_ID = 3
PRE_TOURNAMENT_DATE = "2026-02-26"

MC_PLAYERS = {
    "sam_ryder", "davis_riley", "luke_clanton", "mac_meissner", "webb_simpson",
    "lanto_griffin", "michael_thorbjornsen", "doug_ghim", "kris_ventura",
    "david_lipsky", "gordon_sargent", "chandler_blanchet", "kevin_yu",
    "john_vanderlaan", "peter_malnati", "davis_chatfield", "erik_van_rooyen",
    "gary_woodland", "matt_kuchar", "adam_svensson", "paul_waring",
    "stephan_jaeger", "jesper_svensson", "vince_whaley", "chris_kirk",
    "neal_shipley", "justin_lower", "brice_garnett", "andrew_putnam",
    "danny_willett", "adam_hadwin", "camilo_villegas", "johnny_keefer",
    "sh_kim", "charley_hoffman", "brandt_snedeker", "kensei_hirata",
    "blades_brown", "nick_dunlap", "jeffrey_kang", "karl_vilips",
    "justin_hicks", "harry_higgs", "kh_lee", "christo_lamprecht",
    "aaron_wise", "rico_hoey", "marcelo_rozo", "brendon_todd",
    "sami_valimaki", "rafael_campos", "frankie_capan_iii", "cam_davis",
    "isaiah_salinda", "alejandro_tosti", "keita_nakajima",
}

ACTUAL_RESULTS = {
    "nico_echavarria": 1,
    "taylor_moore": 2, "shane_lowry": 2, "austin_smotherman": 2,
    "ricky_castillo": 5,
    "nicolai_hojgaard": 6, "william_mouw": 6, "keith_mitchell": 6,
    "brooks_koepka": 9, "rasmus_hojgaard": 9, "matti_schmid": 9, "joel_dahmen": 9,
    "pontus_nyholm": 13, "max_homa": 13, "patton_kizzire": 13, "aj_ewart": 13,
    "matthieu_pavon": 17, "sudarshan_yellamaraju": 17, "chad_ramey": 17,
    "zecheng_dou": 17, "takumi_kanaya": 17, "kristoffer_reitan": 17,
    "jordan_smith": 23, "ryan_gerard": 23, "mackenzie_hughes": 23,
    "zach_bauchou": 23, "kevin_roy": 23, "adrien_dumont_de_chassart": 23,
    "mark_hubbard": 23, "aaron_rai": 23, "beau_hossler": 23,
    "haotong_li": 32, "david_ford": 32, "daniel_berger": 32,
    "kevin_streelman": 32, "jimmy_stanger": 32,
    "christiaan_bezuidenhout": 37, "eric_cole": 37, "steven_fisk": 37,
    "danny_walker": 40, "max_mcgreevy": 40, "patrick_fishburn": 40,
    "matt_wallace": 40, "austin_eckroat": 40, "dan_brown": 40,
    "hank_lebioda": 40, "garrick_higgo": 40, "ben_silverman": 40,
    "rasmus_neergaard-petersen": 40, "lee_hodges": 40, "thorbjorn_olesen": 40,
    "carson_young": 52, "alex_smalley": 52, "seamus_power": 52, "michael_brennan": 52,
    "emiliano_grillo": 56, "chan_kim": 56, "adrien_saddier": 56,
    "tom_kim": 59,
    "adam_schenk": 60, "davis_thompson": 60,
    "billy_horschel": 62,
    "jackson_suber": 63, "john_parry": 63, "chandler_phillips": 63,
    "dylan_wu": 66,
    "joe_highsmith": 67,
}

ALL_IN_FIELD = set(ACTUAL_RESULTS.keys()) | MC_PLAYERS


def was_in_field(player_key: str) -> bool:
    return player_key in ALL_IN_FIELD


def did_hit(player_key: str, bet_type: str) -> bool:
    pos = ACTUAL_RESULTS.get(player_key)
    if pos is None:
        return False
    if bet_type == "outright":
        return pos == 1
    if bet_type == "top5":
        return pos <= 5
    if bet_type == "top10":
        return pos <= 12
    if bet_type == "top20":
        return pos <= 22
    if bet_type == "make_cut":
        return pos <= 67
    return False


def load_dg_probs_filtered() -> dict:
    """Load DG sim probs, filtered to confirmed field and renormalized."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT player_key, metric_name, metric_value FROM metrics "
        "WHERE tournament_id = ? AND metric_category = 'sim'",
        (TOURNAMENT_ID,),
    ).fetchall()
    conn.close()

    all_probs: dict[str, dict] = {}
    for r in rows:
        pk = r["player_key"]
        if pk not in all_probs:
            all_probs[pk] = {}
        val = r["metric_value"]
        if val is None:
            continue
        prob = val / 100.0 if val > 1.0 else val
        if prob > 1.0:
            prob = prob / 100.0
        prob = max(0.0001, min(0.9999, prob))

        name = r["metric_name"]
        if "Win" in name:
            key = "outright_ch" if "(CH)" in name else "outright"
        elif "Top 5" in name:
            key = "top5_ch" if "(CH)" in name else "top5"
        elif "Top 10" in name:
            key = "top10_ch" if "(CH)" in name else "top10"
        elif "Top 20" in name:
            key = "top20_ch" if "(CH)" in name else "top20"
        elif "Cut" in name:
            key = "make_cut_ch" if "(CH)" in name else "make_cut"
        else:
            continue
        all_probs[pk][key] = prob

    total_all = len(all_probs)
    filtered = {pk: probs for pk, probs in all_probs.items() if was_in_field(pk)}
    total_filtered = len(filtered)
    removed = total_all - total_filtered

    print(f"  DG sim players: {total_all} total, {total_filtered} in field, {removed} phantom removed")

    # Renormalize
    EXPECTED = {
        "outright": 1.0, "outright_ch": 1.0,
        "top5": 5.0, "top5_ch": 5.0,
        "top10": 10.0, "top10_ch": 10.0,
        "top20": 20.0, "top20_ch": 20.0,
    }

    current_sums: dict[str, float] = {}
    for pk_probs in filtered.values():
        for key, prob in pk_probs.items():
            current_sums[key] = current_sums.get(key, 0.0) + prob

    scale_factors: dict[str, float] = {}
    for bt_key, expected in EXPECTED.items():
        current = current_sums.get(bt_key, 0.0)
        if current < 0.01:
            continue
        if current < expected:
            scale_factors[bt_key] = min(expected / current, 3.0)

    if scale_factors:
        print(f"  Renormalization factors: {', '.join(f'{k}={v:.2f}x' for k, v in sorted(scale_factors.items()))}")
        for pk in filtered:
            for bt_key in list(filtered[pk].keys()):
                if bt_key in scale_factors:
                    filtered[pk][bt_key] = min(
                        filtered[pk][bt_key] * scale_factors[bt_key],
                        0.9999,
                    )

    return filtered


def load_pre_tournament_predictions() -> list[dict]:
    """Load ONLY pre-tournament predictions (Feb 26 timestamp)."""
    conn = get_conn()

    # Show all timestamps for context
    ts_rows = conn.execute(
        "SELECT DISTINCT substr(created_at, 1, 10) as dt, COUNT(*) as cnt "
        "FROM prediction_log WHERE tournament_id = ? GROUP BY dt ORDER BY dt",
        (TOURNAMENT_ID,),
    ).fetchall()
    print("  Prediction log timestamps:")
    for r in ts_rows:
        label = "← USING" if r["dt"] == PRE_TOURNAMENT_DATE else ("← SKIPPED (in-play)" if r["dt"] > PRE_TOURNAMENT_DATE else "← SKIPPED (early)")
        print(f"    {r['dt']}: {r['cnt']} entries {label}")

    rows = conn.execute(
        """SELECT player_key, bet_type, model_prob, dg_prob,
                  market_implied_prob, odds_decimal
           FROM prediction_log
           WHERE tournament_id = ? AND created_at LIKE ?""",
        (TOURNAMENT_ID, PRE_TOURNAMENT_DATE + "%"),
    ).fetchall()
    conn.close()
    print(f"  Using {len(rows)} pre-tournament predictions from {PRE_TOURNAMENT_DATE}")
    return [dict(r) for r in rows]


def decimal_to_american(dec: float) -> int:
    if dec <= 1.0:
        return 0
    if dec >= 2.0:
        return int(round((dec - 1.0) * 100))
    return int(round(-100 / (dec - 1.0)))


def main():
    print("=" * 70)
    print("  BACKTEST: Cognizant Classic — v4.2 Clean Data Pipeline")
    print("=" * 70)
    print()
    print("  === v4.2 Fixes Applied ===")
    print("  1. Pre-tournament odds ONLY (no Round 3 in-play contamination)")
    print("  2. DG probs filtered to confirmed field (no phantom players)")
    print("  3. DG probs renormalized after phantom removal")
    print(f"  4. Blend: {config.BLEND_WEIGHTS['outright']['dg']*100:.0f}% DG / "
          f"{config.BLEND_WEIGHTS['outright']['model']*100:.0f}% model")
    print(f"  5. EV thresholds: outright {config.MARKET_EV_THRESHOLDS['outright']*100:.0f}%, "
          f"top5 {config.MARKET_EV_THRESHOLDS['top5']*100:.0f}%, "
          f"top10 {config.MARKET_EV_THRESHOLDS['top10']*100:.0f}%, "
          f"top20 {config.MARKET_EV_THRESHOLDS['top20']*100:.0f}%")
    print(f"  6. Max total bets: {config.MAX_TOTAL_VALUE_BETS} "
          f"(weak field: {config.MAX_TOTAL_VALUE_BETS_WEAK_FIELD})")
    print()

    dg_probs = load_dg_probs_filtered()
    predictions = load_pre_tournament_predictions()

    if not predictions:
        print("\n  ⛔ No pre-tournament predictions available. Cannot backtest.")
        return

    bet_types_to_test = ["outright", "top5", "top10", "top20"]
    value_bets_by_market: dict[str, list] = {}

    for bt in bet_types_to_test:
        bt_preds = [p for p in predictions if p["bet_type"] == bt]
        if not bt_preds:
            continue

        ev_threshold = config.MARKET_EV_THRESHOLDS.get(bt, config.DEFAULT_EV_THRESHOLD)
        ev_threshold *= config.WEAK_FIELD_EV_MULTIPLIER

        dg_weight = config.BLEND_WEIGHTS[bt]["dg"]
        model_weight = config.BLEND_WEIGHTS[bt]["model"]

        bets = []
        for pred in bt_preds:
            pk = pred["player_key"]
            market_prob = pred["market_implied_prob"]
            odds_dec = pred["odds_decimal"]

            if not market_prob or not odds_dec or odds_dec <= 1.0:
                continue
            if not was_in_field(pk):
                continue

            dg_prob = None
            if pk in dg_probs:
                ch_key = f"{bt}_ch"
                dg_prob = dg_probs[pk].get(ch_key, dg_probs[pk].get(bt))

            old_model_prob = pred["model_prob"]

            if dg_prob is not None:
                old_softmax = (old_model_prob - 0.70 * dg_prob) / 0.30 if 0.30 > 0 else old_model_prob
                old_softmax = max(0.001, min(0.95, old_softmax))
                new_model_prob = dg_weight * dg_prob + model_weight * old_softmax
            else:
                new_model_prob = old_model_prob

            dead_heat = {"top5": 0.05, "top10": 0.10, "top20": 0.08}.get(bt, 0)
            prob_for_ev = new_model_prob * (1.0 - dead_heat)

            american = decimal_to_american(odds_dec)
            ev = prob_for_ev * odds_dec - 1.0

            is_value = ev >= ev_threshold and ev <= config.MAX_CREDIBLE_EV
            prob_ratio = new_model_prob / max(market_prob, 0.0001)
            suspicious = prob_ratio > 10.0 or prob_ratio < 0.1

            bets.append({
                "player_key": pk,
                "player_display": pk.replace("_", " ").title(),
                "bet_type": bt,
                "dg_prob": dg_prob,
                "dg_prob_raw": dg_prob,
                "old_model_prob": old_model_prob,
                "new_model_prob": new_model_prob,
                "market_prob": market_prob,
                "odds_decimal": odds_dec,
                "american_odds": american,
                "ev": ev,
                "ev_pct": f"{ev*100:.1f}%",
                "is_value": is_value and not suspicious,
                "suspicious": suspicious,
                "ev_capped": ev > config.MAX_CREDIBLE_EV,
                "rank": 0,
            })

        bets.sort(key=lambda x: x["ev"], reverse=True)
        value_bets_by_market[bt] = bets

    value_bets_filtered = enforce_diversification(value_bets_by_market, field_strength="weak")

    print()
    print("=" * 70)
    print("  v4.2 VALUE BETS (clean pre-tournament data)")
    print("=" * 70)

    all_value = []
    for bt in bet_types_to_test:
        bets = value_bets_filtered.get(bt, [])
        value_only = [b for b in bets if b.get("is_value")]
        if value_only:
            print(f"\n  --- {bt.upper()} ({len(value_only)} bets) ---")
            for b in value_only:
                hit = did_hit(b["player_key"], bt)
                status = "WIN ✓" if hit else "LOSS"
                american_str = f"+{b['american_odds']}" if b['american_odds'] > 0 else str(b['american_odds'])
                print(f"    {b['player_display']:30s} {american_str:>8s}  "
                      f"EV {b['ev_pct']:>7s}  "
                      f"DG(renorm) {b['new_model_prob']:.3f}  "
                      f"mkt {b['market_prob']:.3f}  "
                      f"-> {status}")
                all_value.append({**b, "hit": hit})

    if not all_value:
        print("\n  NO VALUE BETS found with v4.2 clean-data thresholds.")
        print("  This means: with accurate pre-tournament odds and correctly-scaled")
        print("  DG probabilities, the model sees no genuine edge on this field.")

    # ── Near misses (value before portfolio filter) ──
    near_misses = []
    for bt in bet_types_to_test:
        for b in value_bets_by_market.get(bt, []):
            if not b.get("is_value"):
                continue
            filtered_list = value_bets_filtered.get(bt, [])
            still_value = any(fb.get("is_value") and fb["player_key"] == b["player_key"]
                              for fb in filtered_list)
            if not still_value:
                hit = did_hit(b["player_key"], b["bet_type"])
                near_misses.append({**b, "hit": hit})

    if near_misses:
        print(f"\n  --- Dropped by Portfolio Filter ({len(near_misses)} bets) ---")
        for b in near_misses[:8]:
            hit = did_hit(b["player_key"], b["bet_type"])
            status = "would have WON" if hit else "LOSS"
            american_str = f"+{b['american_odds']}" if b['american_odds'] > 0 else str(b['american_odds'])
            print(f"    {b['player_display']:30s} {b['bet_type']:>8s} {american_str:>8s}  "
                  f"EV {b['ev_pct']:>7s} -> {status}")

    # ── Close-to-value (barely missed EV threshold) ──
    print(f"\n  --- Close to Value (EV > 5% but below threshold) ---")
    for bt in bet_types_to_test:
        for b in value_bets_by_market.get(bt, []):
            if b.get("is_value") or b.get("suspicious"):
                continue
            if b["ev"] > 0.05:
                hit = did_hit(b["player_key"], bt)
                status = "would have WON" if hit else "LOSS"
                american_str = f"+{b['american_odds']}" if b['american_odds'] > 0 else str(b['american_odds'])
                threshold = config.MARKET_EV_THRESHOLDS.get(bt, config.DEFAULT_EV_THRESHOLD) * config.WEAK_FIELD_EV_MULTIPLIER
                print(f"    {b['player_display']:30s} {bt:>8s} {american_str:>8s}  "
                      f"EV {b['ev_pct']:>6s} (need {threshold*100:.0f}%) -> {status}")

    # ── Results ──
    print()
    print("=" * 70)
    print("  RESULTS COMPARISON")
    print("=" * 70)

    wins = sum(1 for b in all_value if b["hit"])
    losses = len(all_value) - wins
    pnl = 0.0
    for b in all_value:
        if b["hit"]:
            pnl += b["odds_decimal"] - 1.0
        else:
            pnl -= 1.0

    print(f"\n  v4.2 Record: {wins}-{losses}")
    print(f"  v4.2 PNL:    {pnl:+.1f}u")
    if all_value:
        print(f"  v4.2 ROI:    {pnl/len(all_value)*100:.1f}%")
    print()
    print(f"  v4.1 Record: 0-6   (contaminated: Feb 28 in-play odds)")
    print(f"  v4.1 PNL:    -6.0u")
    print(f"  v4.1 ROI:    -100.0%")
    print()
    print(f"  v4.0 Record: 1-22  (no thresholds, no field filter)")
    print(f"  v4.0 PNL:    -16.0u")
    print(f"  v4.0 ROI:    -69.6%")

    print()
    print("  === Root Cause Fixes Applied ===")
    print(f"  1. Odds source:    Feb 28 R3 in-play → Feb 26 pre-tournament only")
    print(f"  2. DG field:       182 players (66 phantom) → {len(dg_probs)} confirmed field")
    print(f"  3. DG renorm:      raw (48.6% wasted) → renormalized to correct sums")
    print(f"  4. Blend:          70/30 → 95/5 DG-heavy")
    print(f"  5. EV thresholds:  2-5% → 8-15% (x1.5 weak-field)")
    print(f"  6. Bet volume:     23 bets → capped at {config.MAX_TOTAL_VALUE_BETS_WEAK_FIELD}")


if __name__ == "__main__":
    main()
