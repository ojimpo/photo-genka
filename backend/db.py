import os
import sqlite3
from contextlib import contextmanager

import config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
    day TEXT PRIMARY KEY,          -- YYYY-MM-DD (JST)
    raw_count INTEGER NOT NULL,    -- exiftool が返した生の ImageCount
    count INTEGER NOT NULL,        -- 32K ロールオーバー補正後の単調増加カウント
    asset_id TEXT,                 -- 読み取り元の Immich アセット
    immich_total INTEGER           -- 乖離チェック用: Immich 上の X-E5 アセット総数
);
"""


@contextmanager
def conn():
    os.makedirs(os.path.dirname(config.DB_PATH), exist_ok=True)
    c = sqlite3.connect(config.DB_PATH)
    c.row_factory = sqlite3.Row
    try:
        c.execute(_SCHEMA)
        yield c
        c.commit()
    finally:
        c.close()


def corrected_count(raw: int, prev_corrected: int | None) -> int:
    """16bit ImageCount のロールオーバーを単調増加に補正する。"""
    if prev_corrected is None:
        return raw
    count = raw
    while count < prev_corrected:
        count += config.ROLLOVER_STEP
    return count


def upsert_snapshot(day: str, raw: int, asset_id: str | None, immich_total: int | None):
    with conn() as c:
        row = c.execute(
            "SELECT count FROM snapshots WHERE day < ? ORDER BY day DESC LIMIT 1", (day,)
        ).fetchone()
        prev = row["count"] if row else None
        count = corrected_count(raw, prev)
        c.execute(
            "INSERT INTO snapshots (day, raw_count, count, asset_id, immich_total) VALUES (?,?,?,?,?) "
            "ON CONFLICT(day) DO UPDATE SET raw_count=excluded.raw_count, count=excluded.count, "
            "asset_id=excluded.asset_id, immich_total=excluded.immich_total",
            (day, raw, count, asset_id, immich_total),
        )


def all_snapshots() -> list[dict]:
    with conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM snapshots ORDER BY day")]


def snapshot_for(day: str) -> dict | None:
    with conn() as c:
        r = c.execute("SELECT * FROM snapshots WHERE day = ?", (day,)).fetchone()
        return dict(r) if r else None


def latest_snapshot() -> dict | None:
    with conn() as c:
        r = c.execute("SELECT * FROM snapshots ORDER BY day DESC LIMIT 1").fetchone()
        return dict(r) if r else None


def snapshot_before(day: str) -> dict | None:
    with conn() as c:
        r = c.execute(
            "SELECT * FROM snapshots WHERE day < ? ORDER BY day DESC LIMIT 1", (day,)
        ).fetchone()
        return dict(r) if r else None
