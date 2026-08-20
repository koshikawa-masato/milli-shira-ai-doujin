"""Krea2 Gallery — 生成画像の確認と制作過程の記録

画像:
- GET  /                    UI
- GET  /api/images          画像一覧（新しい順）。?folder= / ?star=true
- GET  /img/{path}          原寸
- GET  /thumb/{path}        サムネイル（webp、/data/thumbs にキャッシュ）
- POST /api/upload          画像アップロード（Bearer GALLERY_TOKEN）。multipart: file, folder, meta(JSON)
- POST /api/star/{path}     お気に入りトグル
- DELETE /api/images/{path} ゴミ箱へ移動（/data/trash。履歴は残る）

履歴（追記専用 /data/history.jsonl。消さない）:
- GET  /api/history         全イベント新しい順。?event=gen|dataset|train_start|train_end|note|trash
- POST /api/event           任意イベント追記（Bearer）。JSON: {"event": "...", ...}
- POST /api/note            UI からのメモ（トークン不要）。JSON: {"text": "...", "ref": "path(optional)"}
- GET  /api/lineage/{path}  画像の系譜: 使った LoRA → 学習 run → 素材画像
"""
from __future__ import annotations

import json
import os
import re
import shutil
import threading
import time
from pathlib import Path

from fastapi import Body, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from PIL import Image

DATA = Path(os.environ.get("DATA_DIR", "/data"))
IMAGES = DATA / "images"
THUMBS = DATA / "thumbs"
TRASH = DATA / "trash"
STARS = DATA / "stars.json"
HISTORY = DATA / "history.jsonl"
TOKEN = os.environ.get("GALLERY_TOKEN", "")
THUMB_SIZE = int(os.environ.get("THUMB_SIZE", "480"))
EXTS = {".png", ".jpg", ".jpeg", ".webp"}
STATIC = Path(__file__).parent / "static"

for d in (IMAGES, THUMBS, TRASH):
    d.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Krea2 Gallery")
_lock = threading.Lock()
_dims_cache: dict[str, tuple[float, int, int]] = {}


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


# ---------- path / stars / meta ----------


def _safe_rel(path: str) -> Path:
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
    txt = full.with_suffix(".txt")
    if txt.exists():
        return {"prompt": txt.read_text().strip()}
    return {}


def _item(full: Path, stars: set[str]) -> dict:
    rel = full.relative_to(IMAGES).as_posix()
    st = full.stat()
    w, h = _dims(full, rel, st.st_mtime)
    folder = full.parent.relative_to(IMAGES).as_posix()
    return {
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


def _scan() -> list[dict]:
    stars = _load_stars()
    items = [
        _item(f, stars)
        for f in IMAGES.rglob("*")
        if f.is_file() and f.suffix.lower() in EXTS
    ]
    items.sort(key=lambda x: x["mtime"], reverse=True)
    return items


# ---------- history ----------


def _append_history(entry: dict) -> dict:
    entry.setdefault("ts", _now())
    with HISTORY.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def _read_history() -> list[dict]:
    if not HISTORY.exists():
        return []
    out = []
    for line in HISTORY.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return out


def _backfill_history() -> None:
    """履歴ファイルが無ければ、既存画像のサイドカーから生成イベントを復元する。"""
    if HISTORY.exists():
        return
    files = sorted(
        (f for f in IMAGES.rglob("*") if f.is_file() and f.suffix.lower() in EXTS),
        key=lambda p: p.stat().st_mtime,
    )
    with _lock:
        for f in files:
            folder = f.parent.relative_to(IMAGES).as_posix()
            _append_history(
                {
                    "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(f.stat().st_mtime)),
                    "event": "gen",
                    "path": f.relative_to(IMAGES).as_posix(),
                    "folder": "" if folder == "." else folder,
                    "meta": _meta(f),
                    "backfilled": True,
                }
            )


def _stage_of(folder: str, meta: dict) -> str:
    if meta.get("stage"):
        return meta["stage"]
    if folder == "dataset" or folder.startswith("dataset/"):
        return "dataset"
    return "gen"


# ---------- routes: images ----------


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
    full = IMAGES / _safe_rel(path)
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
        dest = dest_dir / f"{dest.stem}-{int(time.time())}{dest.suffix}"
    m: dict = {}
    if meta:
        try:
            m = json.loads(meta)
        except json.JSONDecodeError:
            m = {"raw": meta}
    with _lock:
        with dest.open("wb") as f:
            shutil.copyfileobj(file.file, f)
        rel = dest.relative_to(IMAGES).as_posix()
        if m:
            m.setdefault("uploaded_at", _now())
            dest.with_suffix(dest.suffix + ".json").write_text(
                json.dumps(m, ensure_ascii=False, indent=1)
            )
        _append_history(
            {"event": _stage_of(folder, m), "path": rel, "folder": folder, "meta": m}
        )
    return {"ok": True, "path": rel}


@app.post("/api/star/{path:path}")
def star(path: str):
    rel = _safe_rel(path).as_posix()
    with _lock:
        s = _load_stars()
        on = rel not in s
        (s.add if on else s.discard)(rel)
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
        _append_history({"event": "trash", "path": rel.as_posix()})
    return {"ok": True}


# ---------- routes: history / lineage ----------


@app.get("/api/history")
def api_history(event: str | None = None, limit: int = 2000):
    hist = _read_history()
    trashed = {h.get("path") for h in hist if h.get("event") == "trash"}
    out = []
    for h in reversed(hist):
        if event and h.get("event") != event:
            continue
        e = dict(h)
        if e.get("path"):
            e["exists"] = (IMAGES / e["path"]).exists()
            e["trashed"] = e["path"] in trashed
        out.append(e)
        if len(out) >= limit:
            break
    return {"items": out, "total": len(out)}


@app.post("/api/event")
def api_event(body: dict = Body(...), authorization: str | None = Header(default=None)):
    _check_token(authorization)
    if not body.get("event"):
        raise HTTPException(400, "event required")
    with _lock:
        e = _append_history(dict(body))
    return {"ok": True, "entry": e}


@app.post("/api/note")
def api_note(body: dict = Body(...)):
    text = (body.get("text") or "").strip()
    if not text:
        raise HTTPException(400, "text required")
    with _lock:
        e = _append_history({"event": "note", "text": text, "ref": body.get("ref") or None})
    return {"ok": True, "entry": e}


def _run_of(meta: dict) -> tuple[str | None, int | None]:
    """LoRA ファイル名から run 名と step を取る。kuropanda_krea2-001200.safetensors -> (kuropanda_krea2, 1200)"""
    if meta.get("run"):
        return meta["run"], meta.get("step")
    lora = meta.get("lora")
    if not lora:
        return None, None
    b = Path(str(lora)).name
    mt = re.match(r"^(.+?)-(\d{6})\.safetensors$", b)
    if mt:
        return mt.group(1), int(mt.group(2))
    return b.replace(".safetensors", ""), None


@app.get("/api/lineage/{path:path}")
def api_lineage(path: str):
    rel = _safe_rel(path).as_posix()
    full = IMAGES / rel
    meta = _meta(full) if full.exists() else {}
    run, step = _run_of(meta)
    hist = _read_history()
    trains = [h for h in hist if h.get("event") in ("train_start", "train_end") and h.get("run") == run] if run else []
    dataset_folder = None
    for h in trains:
        if h.get("dataset_folder"):
            dataset_folder = h["dataset_folder"]
    if run and dataset_folder is None:
        dataset_folder = "dataset"
    stars = _load_stars()
    dataset_items = []
    if dataset_folder:
        d = IMAGES / dataset_folder
        if d.exists():
            dataset_items = sorted(
                (_item(f, stars) for f in d.rglob("*") if f.is_file() and f.suffix.lower() in EXTS),
                key=lambda x: x["name"],
            )
    # 同じ run の他チェックポイント比較画像
    siblings = []
    if run:
        for h in reversed(hist):
            if h.get("event") == "gen" and h.get("path") != rel:
                r, s = _run_of(h.get("meta") or {})
                if r == run and (IMAGES / h["path"]).exists():
                    siblings.append({"path": h["path"], "step": s, "seed": (h.get("meta") or {}).get("seed"), "prompt": (h.get("meta") or {}).get("prompt")})
    notes = [h for h in hist if h.get("event") == "note" and h.get("ref") == rel]
    return {
        "path": rel,
        "meta": meta,
        "run": run,
        "step": step,
        "train_events": trains,
        "dataset_folder": dataset_folder,
        "dataset": dataset_items,
        "siblings": siblings[:60],
        "notes": notes,
    }


@app.get("/healthz")
def healthz():
    return JSONResponse({"ok": True})


_backfill_history()
