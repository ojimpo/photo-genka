"""日次スナップショット取得とバックフィル。

毎日 JST 23:30 に「Immich の最新 X-E5 アセット → exiftool → SQLite」を実行する。
初回起動時は購入日から今日まで、各日の最後の1枚をサンプリングして遡って埋める。
"""
import asyncio
import logging
from datetime import datetime, time, timedelta, timezone

import config
import db
import immich
import stats

log = logging.getLogger("genka.snapshot")

SNAPSHOT_AT = time(23, 30)
REFRESH_WINDOW_DAYS = 14  # オンデマンド更新で遡って見直す日数（日次ジョブは全期間）


def _day_end_utc_iso(day) -> str:
    """JST のその日の終わりを UTC ISO 文字列で返す（takenBefore 用）。"""
    end = datetime.combine(day + timedelta(days=1), time(0, 0), tzinfo=stats.JST)
    return end.astimezone(timezone.utc).isoformat()


def take_snapshot(day=None) -> bool:
    """指定日（省略時は今日）のスナップショットを取る。成功したら True。"""
    if not immich.enabled():
        log.info("IMMICH_API_KEY 未設定のためスナップショットをスキップ")
        return False
    day = day or stats.today_jst()
    result = immich.latest_image_count(taken_before=_day_end_utc_iso(day))
    if result is None:
        log.warning("%s: ImageCount を読めるアセットがありません", day)
        return False
    count, asset_id, last_taken_at = result
    total = immich.asset_count() if day == stats.today_jst() else None
    db.upsert_snapshot(day.isoformat(), count, asset_id, total, last_taken_at)
    log.info("%s: ImageCount=%s asset=%s immich_total=%s last_taken=%s",
             day, count, asset_id, total, last_taken_at)
    return True


def refresh_today() -> bool:
    """オンデマンドで今日のスナップショットを取り直す（/api/daily-shots?fresh=1 用）。

    Immich の最新アセットが前回読んだものと同じなら ImageCount も同じはずなので、
    オリジナルのダウンロードを省略する（メタデータ検索1回だけで済む）。
    """
    if not immich.enabled():
        return False
    reconcile(window_days=REFRESH_WINDOW_DAYS)
    return True


def reconcile(window_days: int | None = None):
    """各日のスナップショットを「その日の終わりまでに撮られた最新の1枚」で取り直す。

    草は日次差分なので、撮影日ベースにするには後から Immich に取り込まれた写真を
    過去の日に反映する必要がある。メタデータ検索1回で最新アセットが保存済みと同じなら
    オリジナルのダウンロードを省く。window_days が None なら購入日から全期間。
    """
    if not immich.enabled():
        return
    today = stats.today_jst()
    start = config.PURCHASE_DATE
    if window_days is not None:
        start = max(start, today - timedelta(days=window_days))
    day = start
    while day <= today:
        try:
            existing = db.snapshot_for(day.isoformat())
            assets = immich.search_assets(taken_before=_day_end_utc_iso(day), size=1)
            if not (existing and assets and assets[0]["id"] == existing.get("asset_id")):
                take_snapshot(day)
        except Exception:
            log.exception("%s の撮影日ベース再計算に失敗", day)
        day += timedelta(days=1)


def backfill():
    """購入日から今日まで、スナップショットのない日を各日最後の1枚で埋める。"""
    if not immich.enabled():
        return
    have = {s["day"] for s in db.all_snapshots()}
    day = config.PURCHASE_DATE
    today = stats.today_jst()
    while day <= today:
        if day.isoformat() not in have:
            try:
                take_snapshot(day)
            except Exception:
                log.exception("%s のバックフィルに失敗", day)
        day += timedelta(days=1)


def backfill_last_taken():
    """last_taken_at 列の追加前に取った行を、保存済み asset_id から埋め直す。"""
    if not immich.enabled():
        return
    for row in db.rows_missing_last_taken():
        try:
            taken = immich.asset_local_datetime(row["asset_id"])
        except Exception:
            log.exception("%s の撮影日時バックフィルに失敗", row["day"])
            continue
        if taken:
            db.set_last_taken(row["day"], taken)


async def run():
    """起動時バックフィル → 毎日 JST 23:30 のスナップショットループ。"""
    await asyncio.to_thread(backfill)
    await asyncio.to_thread(reconcile)
    await asyncio.to_thread(backfill_last_taken)
    while True:
        now = datetime.now(stats.JST)
        target = datetime.combine(now.date(), SNAPSHOT_AT, tzinfo=stats.JST)
        if now >= target:
            target += timedelta(days=1)
        await asyncio.sleep((target - now).total_seconds())
        try:
            await asyncio.to_thread(take_snapshot)
            await asyncio.to_thread(reconcile)
        except Exception:
            log.exception("日次スナップショットに失敗")
