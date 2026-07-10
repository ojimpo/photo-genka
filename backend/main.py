import asyncio
import logging
import os
import tempfile
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles

import config
import exif
import snapshot_job
import stats

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    job = asyncio.create_task(snapshot_job.run())
    yield
    job.cancel()


app = FastAPI(title="photo-genka", lifespan=lifespan)


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/api/stats")
def get_stats():
    return stats.build_stats()


@app.get("/api/history")
def get_history():
    return stats.build_history()


@app.post("/api/inspect")
async def inspect(file: UploadFile):
    """ドロップされた写真の ImageCount を読み「何枚目・撮影時点の単価」を返す。

    画像は即時破棄し、保存しない。
    """
    body = await file.read()
    if len(body) > config.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(413, f"ファイルが大きすぎます（上限 {config.MAX_UPLOAD_MB}MB）")

    suffix = os.path.splitext(file.filename or "")[1] or ".bin"
    fd, path = tempfile.mkstemp(suffix=suffix)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(body)
        raw = exif.read_image_count(path)
    finally:
        os.unlink(path)

    if raw is None:
        raise HTTPException(422, "この写真から ImageCount を読めませんでした（X-E5 の撮って出しJPEG/HEIF/RAFが対象です）")

    current = stats.build_stats()
    # ドロップ写真の枚数目はロールオーバー補正なしの生値ベース（周回情報がないため）
    price_then = round(config.TOTAL_PRICE_JPY / raw, 1) if raw > 0 else None
    return {
        "image_count": raw,
        "price_then": price_then,
        "price_now": current["price_per_shot"],
        "count_now": current["count"],
    }


class CachedStaticFiles(StaticFiles):
    """CF が旧アセットを掴み続けないよう、種類別に Cache-Control を明示する。"""

    MAX_AGE = {".css": 300, ".js": 300, ".html": 60, ".png": 86400, ".svg": 86400}

    def file_response(self, full_path, *args, **kwargs):
        response = super().file_response(full_path, *args, **kwargs)
        age = self.MAX_AGE.get(os.path.splitext(str(full_path))[1], 300)
        response.headers["Cache-Control"] = f"public, max-age={age}"
        return response


app.mount("/", CachedStaticFiles(directory=os.environ.get("STATIC_DIR", "/app/frontend"), html=True), name="static")
