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
    immich_total INTEGER,          -- 乖離チェック用: Immich 上の X-E5 アセット総数
    last_taken_at TEXT             -- その時点で最後に撮った1枚の撮影日時（JSTのローカル壁時計）
);
"""


def _migrate(c):
    """既存 DB への列追加。CREATE TABLE IF NOT EXISTS は既存テーブルを更新しないため必要。"""
    cols = {r["name"] for r in c.execute("PRAGMA table_info(snapshots)")}
    if "last_taken_at" not in cols:
        c.execute("ALTER TABLE snapshots ADD COLUMN last_taken_at TEXT")


@contextmanager
def conn():
    os.makedirs(os.path.dirname(config.DB_PATH), exist_ok=True)
    c = sqlite3.connect(config.DB_PATH)
    c.row_factory = sqlite3.Row
    try:
        c.execute(_SCHEMA)
        _migrate(c)
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


def upsert_snapshot(day: str, raw: int, asset_id: str | None, immich_total: int | None,
                    last_taken_at: str | None = None):
    with conn() as c:
        row = c.execute(
            "SELECT count FROM snapshots WHERE day < ? ORDER BY day DESC LIMIT 1", (day,)
        ).fetchone()
        prev = row["count"] if row else None
        count = corrected_count(raw, prev)
        c.execute(
            "INSERT INTO snapshots (day, raw_count, count, asset_id, immich_total, last_taken_at) "
            "VALUES (?,?,?,?,?,?) "
            "ON CONFLICT(day) DO UPDATE SET raw_count=excluded.raw_count, count=excluded.count, "
            "asset_id=excluded.asset_id, immich_total=excluded.immich_total, "
            "last_taken_at=COALESCE(excluded.last_taken_at, snapshots.last_taken_at)",
            (day, raw, count, asset_id, immich_total, last_taken_at),
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


def rows_missing_last_taken() -> list[dict]:
    """last_taken_at 列の追加前に取ったスナップショット（asset_id はあるが日時が無い行）。"""
    with conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT day, asset_id FROM snapshots "
            "WHERE last_taken_at IS NULL AND asset_id IS NOT NULL ORDER BY day"
        )]


def set_last_taken(day: str, last_taken_at: str):
    with conn() as c:
        c.execute("UPDATE snapshots SET last_taken_at = ? WHERE day = ?", (last_taken_at, day))
