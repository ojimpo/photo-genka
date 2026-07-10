"""Immich API クライアント。

分母の一次ソースは「最新 X-E5 アセットのオリジナルを exiftool で読んだ ImageCount」。
アセット数はあくまで乖離チェック用（取り込み漏れ・カメラ内削除の検出）。
"""
import logging
import os
import tempfile

import httpx

import config
import exif

log = logging.getLogger("genka.immich")


def enabled() -> bool:
    return bool(config.IMMICH_API_KEY)


def _client() -> httpx.Client:
    return httpx.Client(
        base_url=config.IMMICH_URL,
        headers={"x-api-key": config.IMMICH_API_KEY},
        timeout=60,
    )


def search_assets(taken_before: str | None = None, taken_after: str | None = None,
                  size: int = 1) -> list[dict]:
    """撮影日時の降順で X-E5 アセットを検索する。"""
    body: dict = {"model": config.CAMERA_MODEL, "size": size, "order": "desc"}
    if taken_before:
        body["takenBefore"] = taken_before
    if taken_after:
        body["takenAfter"] = taken_after
    with _client() as c:
        r = c.post("/api/search/metadata", json=body)
        r.raise_for_status()
        return r.json().get("assets", {}).get("items", [])


def asset_count() -> int | None:
    with _client() as c:
        r = c.post("/api/search/statistics", json={"model": config.CAMERA_MODEL})
        if r.status_code != 200:
            log.warning("search/statistics returned %s", r.status_code)
            return None
        return r.json().get("total")


def read_asset_image_count(asset_id: str) -> int | None:
    """アセットのオリジナルをダウンロードして ImageCount を読み、即時破棄する。"""
    with _client() as c:
        r = c.get(f"/api/assets/{asset_id}/original")
        r.raise_for_status()
        fd, path = tempfile.mkstemp(suffix=".bin")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(r.content)
            return exif.read_image_count(path)
        finally:
            os.unlink(path)


def latest_image_count(taken_before: str | None = None) -> tuple[int, str] | None:
    """(ImageCount, asset_id) を返す。読めるアセットが見つかるまで数件さかのぼる。"""
    assets = search_assets(taken_before=taken_before, size=5)
    for asset in assets:
        count = read_asset_image_count(asset["id"])
        if count is not None:
            return count, asset["id"]
        log.warning("asset %s から ImageCount を読めませんでした", asset["id"])
    return None
