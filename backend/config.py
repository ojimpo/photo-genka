import os
from datetime import date


def _int(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


TOTAL_PRICE_JPY = _int("TOTAL_PRICE_JPY", 248310)
PURCHASE_DATE = date.fromisoformat(os.environ.get("PURCHASE_DATE", "2026-07-06"))
FILM_PRICE_JPY = _int("FILM_PRICE_JPY", 2500)
FILM_DEV_PRICE_JPY = _int("FILM_DEV_PRICE_JPY", 1830)
FILM_SHOTS_PER_ROLL = _int("FILM_SHOTS_PER_ROLL", 24)
# SMBC ショッピングクレジット（カメラのキタムラ）48回無金利
INSTALLMENTS = _int("INSTALLMENTS", 48)

IMMICH_URL = os.environ.get("IMMICH_URL", "http://host.docker.internal:2283")
IMMICH_API_KEY = os.environ.get("IMMICH_API_KEY", "")
CAMERA_MODEL = os.environ.get("CAMERA_MODEL", "X-E5")

MAX_UPLOAD_MB = _int("MAX_UPLOAD_MB", 120)
DB_PATH = os.environ.get("DB_PATH", "/app/data/genka.db")

# ImageCount は 16bit カウンタ（32K ロールオーバー補正の単位）
ROLLOVER_STEP = 32768

# アタリ（塗装剥げ）マイルストーン。
# Immich 実測の iPhone 年間撮影実績（2025-26: 3,429枚 / 2024-25: 3,132枚 ≒ 3,000枚/年）から較正:
# 半年 → 1年 → 2年 → 4年 → 10年相当で段階的に「相棒」になっていく
ATARI_MILESTONES = [1500, 3000, 6000, 12000, 30000]


def film_price_per_shot() -> float:
    return (FILM_PRICE_JPY + FILM_DEV_PRICE_JPY) / FILM_SHOTS_PER_ROLL
