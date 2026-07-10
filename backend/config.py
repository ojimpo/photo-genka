import os
from datetime import date


def _int(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


TOTAL_PRICE_JPY = _int("TOTAL_PRICE_JPY", 248310)
PURCHASE_DATE = date.fromisoformat(os.environ.get("PURCHASE_DATE", "2026-07-06"))
FILM_PRICE_JPY = _int("FILM_PRICE_JPY", 2500)
FILM_DEV_PRICE_JPY = _int("FILM_DEV_PRICE_JPY", 1830)
FILM_SHOTS_PER_ROLL = _int("FILM_SHOTS_PER_ROLL", 24)
JACCS_INSTALLMENTS = _int("JACCS_INSTALLMENTS", 48)

IMMICH_URL = os.environ.get("IMMICH_URL", "http://host.docker.internal:2283")
IMMICH_API_KEY = os.environ.get("IMMICH_API_KEY", "")
CAMERA_MODEL = os.environ.get("CAMERA_MODEL", "X-E5")

MAX_UPLOAD_MB = _int("MAX_UPLOAD_MB", 120)
DB_PATH = os.environ.get("DB_PATH", "/app/data/genka.db")

# ImageCount は 16bit カウンタ（32K ロールオーバー補正の単位）
ROLLOVER_STEP = 32768

# アタリ（塗装剥げ）マイルストーン。iPhone の年間撮影実績から較正予定の仮値
ATARI_MILESTONES = [3000, 10000, 30000, 65536, 100000]


def film_price_per_shot() -> float:
    return (FILM_PRICE_JPY + FILM_DEV_PRICE_JPY) / FILM_SHOTS_PER_ROLL
