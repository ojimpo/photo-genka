import json
import subprocess


def read_image_count(path: str) -> int | None:
    """Fujifilm Maker Notes 0x1438 (ImageCount) を exiftool で読む。"""
    proc = subprocess.run(
        ["exiftool", "-j", "-n", "-MakerNotes:ImageCount", "-ImageCount", path],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if proc.returncode != 0:
        return None
    try:
        data = json.loads(proc.stdout)[0]
    except (json.JSONDecodeError, IndexError):
        return None
    value = data.get("ImageCount")
    return int(value) if isinstance(value, (int, float)) else None
