"""Krea2 Gallery — 生成画像の確認用 WebApp

- GET  /                    ギャラリー UI
- GET  /api/images          画像一覧（新しい順）。?folder= で絞り込み
- GET  /img/{path}          原寸画像
- GET  /thumb/{path}        サムネイル（webp, 長辺 THUMB_SIZE px、/data/thumbs にキャッシュ）
- POST /api/upload          画像アップロード（Bearer GALLERY_TOKEN 必須）
                            multipart: file, folder(optional), meta(optional JSON 文字列)
- POST /api/star/{path}     お気に入りトグル
- DELETE /api/images/{path} 画像削除（UI から。ゴミ箱 /data/trash へ移動）
"""
from __future__ import annotations

import json
import os
import re
import shutil
import threading
import time
from pathlib import Path

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from PIL import Image

DATA = Path(os.environ.get("DATA_DIR", "/data"))
IMAGES = DATA / "images"
THUMBS = DATA / "thumbs"
TRASH = DATA / "trash"
STARS = DATA / "stars.json"
TOKEN = os.environ.get("GALLERY_TOKEN", "")
THUMB_SIZE = int(os.environ.get("THUMB_SIZE", "480"))
EXTS = {".png", ".jpg", ".jpeg", ".webp"}

for d in (IMAGES, THUMBS, TRASH):
    d.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Krea2 Gallery")
_lock = threading.Lock()
_dims_cache: dict[str, tuple[float, int, int]] = {}  # rel -> (mtime, w, h)

STATIC = Path(__file__).parent / "static"


def _safe_rel(path: str) -> Path:
    """/data/images 配下に閉じた相対パスにする。"""
    rel = Path(path)
    if rel.is_absolute() or ".." in rel.parts:
        raise HTTPException(400, "bad path")
    full = (IMAGES / rel).resolve()
    if IMAGES.resolve() not in full.parents:
        raise HTTPException(400, "bad path")
    return rel


def _load_stars() -> set[str]:
    if STARS.exists():
        try:
            return set(json.loads(STARS.read_text()))
        except Exception:
            return set()
    return set()


def _save_stars(s: set[str]) -> None:
    STARS.write_text(json.dumps(sorted(s), ensure_ascii=False, indent=1))


def _dims(full: Path, rel: str, mtime: float) -> tuple[int, int]:
    c = _dims_cache.get(rel)
    if c and c[0] == mtime:
        return c[1], c[2]
    try:
        with Image.open(full) as im:
            w, h = im.size
    except Exception:
        w, h = 0, 0
    _dims_cache[rel] = (mtime, w, h)
    return w, h


def _meta(full: Path) -> dict:
    side = full.with_suffix(full.suffix + ".json")
    if side.exists():
        try:
            return json.loads(side.read_text())
        except Exception:
            pass
    # 同名 .txt があればプロンプトとして扱う
    txt = full.with_suffix(".txt")
    if txt.exists():
        return {"prompt": txt.read_text().strip()}
    return {}


def _scan() -> list[dict]:
    stars = _load_stars()
    items = []
    for full in IMAGES.rglob("*"):
        if not full.is_file() or full.suffix.lower() not in EXTS:
            continue
        rel = full.relative_to(IMAGES).as_posix()
        st = full.stat()
        w, h = _dims(full, rel, st.st_mtime)
        folder = full.parent.relative_to(IMAGES).as_posix()
        items.append(
            {
                "path": rel,
                "name": full.name,
                "folder": "" if folder == "." else folder,
                "mtime": st.st_mtime,
                "size": st.st_size,
                "w": w,
                "h": h,
                "meta": _meta(full),
                "star": rel in stars,
            }
        )
    items.sort(key=lambda x: x["mtime"], reverse=True)
    return items


@app.get("/", response_class=HTMLResponse)
def index():
    return (STATIC / "index.html").read_text(encoding="utf-8")


@app.get("/api/images")
def api_images(folder: str | None = None, star: bool = False):
    items = _scan()
    folders = sorted({i["folder"] for i in items})
    if folder is not None:
        items = [i for i in items if i["folder"] == folder]
    if star:
        items = [i for i in items if i["star"]]
    return {"folders": folders, "items": items, "total": len(items)}


@app.get("/img/{path:path}")
def img(path: str):
    rel = _safe_rel(path)
    full = IMAGES / rel
    if not full.exists():
        raise HTTPException(404)
    return FileResponse(full)


@app.get("/thumb/{path:path}")
def thumb(path: str):
    rel = _safe_rel(path)
    full = IMAGES / rel
    if not full.exists():
        raise HTTPException(404)
    t = THUMBS / (rel.as_posix() + ".webp")
    if not t.exists() or t.stat().st_mtime < full.stat().st_mtime:
        t.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(full) as im:
            im = im.convert("RGB")
            im.thumbnail((THUMB_SIZE, THUMB_SIZE))
            tmp = t.with_suffix(".tmp.webp")
            im.save(tmp, "WEBP", quality=82)
            tmp.replace(t)
    return FileResponse(t, media_type="image/webp")


def _check_token(authorization: str | None):
    if not TOKEN:
        raise HTTPException(503, "GALLERY_TOKEN not configured")
    if authorization != f"Bearer {TOKEN}":
        raise HTTPException(401, "unauthorized")


_name_re = re.compile(r"[^A-Za-z0-9._-]+")


@app.post("/api/upload")
async def upload(
    file: UploadFile = File(...),
    folder: str = Form(""),
    meta: str = Form(""),
    authorization: str | None = Header(default=None),
):
    _check_token(authorization)
    name = _name_re.sub("_", Path(file.filename or "image.png").name)
    if Path(name).suffix.lower() not in EXTS:
        raise HTTPException(400, "unsupported file type")
    folder = folder.strip("/")
    if folder:
        _safe_rel(folder)
    dest_dir = IMAGES / folder if folder else IMAGES
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / name
    if dest.exists():
        stem, suf = dest.stem, dest.suffix
        dest = dest_dir / f"{stem}-{int(time.time())}{suf}"
    with _lock:
        with dest.open("wb") as f:
            shutil.copyfileobj(file.file, f)
        if meta:
            try:
                m = json.loads(meta)
            except json.JSONDecodeError:
                m = {"raw": meta}
            m.setdefault("uploaded_at", time.strftime("%Y-%m-%dT%H:%M:%S"))
            dest.with_suffix(dest.suffix + ".json").write_text(
                json.dumps(m, ensure_ascii=False, indent=1)
            )
    rel = dest.relative_to(IMAGES).as_posix()
    return {"ok": True, "path": rel}


@app.post("/api/star/{path:path}")
def star(path: str):
    rel = _safe_rel(path).as_posix()
    with _lock:
        s = _load_stars()
        if rel in s:
            s.discard(rel)
            on = False
        else:
            s.add(rel)
            on = True
        _save_stars(s)
    return {"path": rel, "star": on}


@app.delete("/api/images/{path:path}")
def delete(path: str):
    rel = _safe_rel(path)
    full = IMAGES / rel
    if not full.exists():
        raise HTTPException(404)
    with _lock:
        dst = TRASH / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(full), str(dst))
        side = full.with_suffix(full.suffix + ".json")
        if side.exists():
            shutil.move(str(side), str(dst.with_suffix(dst.suffix + ".json")))
        t = THUMBS / (rel.as_posix() + ".webp")
        if t.exists():
            t.unlink()
        s = _load_stars()
        s.discard(rel.as_posix())
        _save_stars(s)
    return {"ok": True}


@app.get("/healthz")
def healthz():
    return JSONResponse({"ok": True})
