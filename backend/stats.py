import json
import math
import os
from datetime import date, datetime, timedelta, timezone

import config
import db

JST = timezone(timedelta(hours=9))

with open(os.path.join(os.path.dirname(__file__), "trivia.json"), encoding="utf-8") as f:
    TRIVIA = sorted(json.load(f), key=lambda t: t["threshold"])


def today_jst() -> date:
    return datetime.now(JST).date()


def price_per_shot(count: int) -> float:
    return config.TOTAL_PRICE_JPY / count if count > 0 else float("inf")


def trivia_for(count: int) -> dict | None:
    hit = None
    for t in TRIVIA:
        if count >= t["threshold"]:
            hit = t
        else:
            break
    return hit


def jaccs_progress(today: date) -> dict:
    """支払進捗（演出専用。単価計算には使わない）。初回支払は購入月の翌月と仮定。"""
    start_y, start_m = config.PURCHASE_DATE.year, config.PURCHASE_DATE.month + 1
    if start_m > 12:
        start_y, start_m = start_y + 1, 1
    months = (today.year - start_y) * 12 + (today.month - start_m)
    paid = max(0, min(config.JACCS_INSTALLMENTS, months + 1))
    return {
        "paid": paid,
        "total": config.JACCS_INSTALLMENTS,
        "ratio": paid / config.JACCS_INSTALLMENTS,
    }


def sparkle_opacity(today: date) -> float:
    """キラキラ減衰: 購入から1年でゼロ（時間ベース）。"""
    days = (today - config.PURCHASE_DATE).days
    return max(0.0, 1.0 - days / 365)


def atari(count: int) -> dict:
    """アタリ（塗装剥げ）: 枚数マイルストーンで段階的に出現。"""
    passed = [m for m in config.ATARI_MILESTONES if count >= m]
    upcoming = [m for m in config.ATARI_MILESTONES if count < m]
    return {
        "level": len(passed),
        "next_milestone": upcoming[0] if upcoming else None,
        "shots_to_next": (upcoming[0] - count) if upcoming else None,
    }


def film_stats(count: int) -> dict:
    per_shot = config.film_price_per_shot()
    current = price_per_shot(count)
    breakeven_count = math.ceil(config.TOTAL_PRICE_JPY / per_shot)
    result = {
        "film_price_per_shot": round(per_shot, 1),
        "film_roll_price": config.FILM_PRICE_JPY + config.FILM_DEV_PRICE_JPY,
        "shots_per_roll": config.FILM_SHOTS_PER_ROLL,
        "rolls_equivalent": round(count / config.FILM_SHOTS_PER_ROLL, 1),
        "breakeven_count": breakeven_count,
    }
    if current <= per_shot:
        result["cheaper_than_film"] = True
        result["ratio"] = round(per_shot / current, 1)
        saved = per_shot * count - config.TOTAL_PRICE_JPY
        result["rolls_saved"] = round(saved / (config.FILM_PRICE_JPY + config.FILM_DEV_PRICE_JPY), 1)
    else:
        result["cheaper_than_film"] = False
        result["shots_to_breakeven"] = breakeven_count - count
    return result


def build_stats() -> dict:
    today = today_jst()
    latest = db.latest_snapshot()
    mock = latest is None
    if mock:
        # Immich API キー未設定・スナップショットなしの間は仮データで UI を成立させる
        latest = {"day": today.isoformat(), "count": 217, "raw_count": 217,
                  "asset_id": None, "immich_total": None}

    count = latest["count"]
    price = price_per_shot(count)

    prev = db.snapshot_before(latest["day"]) if not mock else None
    delta = None
    if prev:
        delta = round(price - price_per_shot(prev["count"]), 2)

    return {
        "mock": mock,
        "as_of": latest["day"],
        "total_price": config.TOTAL_PRICE_JPY,
        "purchase_date": config.PURCHASE_DATE.isoformat(),
        "count": count,
        "price_per_shot": round(price, 1),
        "delta_from_prev": delta,
        "immich_total": latest.get("immich_total"),
        "film": film_stats(count),
        "trivia": trivia_for(count),
        "jaccs": jaccs_progress(today),
        "sparkle_opacity": round(sparkle_opacity(today), 3),
        "atari": atari(count),
    }


def build_history() -> list[dict]:
    return [
        {"day": s["day"], "count": s["count"],
         "price": round(price_per_shot(s["count"]), 2)}
        for s in db.all_snapshots() if s["count"] > 0
    ]
