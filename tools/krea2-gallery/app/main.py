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
ジョブ（iPhone からの指示 → WSL2 ワーカーが実行）:
- GET  /api/jobs            一覧（新しい順）。GET /api/jobs/{id}?tail=200 で詳細+ログ末尾
- POST /api/jobs            投入 JSON: {"type": "gen|train|compare|edit", "params": {...}, "note": "..."}
                            edit は RunPod Serverless（runpod_worker.py が中継）。params: prompt, control[先頭=元画像, 以降=参照], seed, width, height, steps, guidance, folder
- POST /api/jobs/{id}/cancel
- GET  /api/jobs/next?worker=   ワーカー用（Bearer）: 次の queued を running にして返す
- POST /api/jobs/{id}/log   ワーカー用（Bearer）: {"lines": [...], "progress": {...}}
- POST /api/jobs/{id}/finish ワーカー用（Bearer）: {"status": "done|failed|cancelled", "result": {...}}
- POST /api/worker/heartbeat ワーカー用（Bearer）: {"gpu": {...}, "loras": [...], "dataset_count": n, "running": id}
- GET  /api/worker          ワーカー状態（最終 heartbeat・GPU・LoRA 一覧）
- GET  /api/graph           系統図: 全画像の派生元（明示 > LoRA run > プロンプト類似で推定）と副次エッジ
- POST /api/parent/{path}   派生元の明示指定 JSON: {"parent": "<path>" | null}
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
    mt = re.match(r"^(.+?)-(?:step)?(\d{6,8})\.safetensors$", b)
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


# ---------- graph (派生関係) ----------

_tok_re = re.compile(r"(\s*,\s*|\s+)")


def _tokens(p: str) -> list[str]:
    return [t for t in _tok_re.split(p or "") if t.strip()]


def _lcs_len(a: list[str], b: list[str]) -> int:
    if not a or not b:
        return 0
    prev = [0] * (len(b) + 1)
    for i in range(len(a) - 1, -1, -1):
        cur = [0] * (len(b) + 1)
        ai = a[i]
        for j in range(len(b) - 1, -1, -1):
            cur[j] = prev[j + 1] + 1 if ai == b[j] else max(prev[j], cur[j + 1])
        prev = cur
    return prev[0]


def _similarity(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return _lcs_len(ta, tb) / max(len(ta), len(tb))


def _write_meta(full: Path, m: dict) -> None:
    full.with_suffix(full.suffix + ".json").write_text(json.dumps(m, ensure_ascii=False, indent=1))


def _build_graph() -> dict:
    items = sorted(_scan(), key=lambda x: x["mtime"])
    by_path = {i["path"]: i for i in items}
    hist = _read_history()
    runs: dict[str, dict] = {}
    for h in hist:
        if h.get("event") == "train_start" and h.get("run"):
            runs.setdefault(h["run"], {})
            runs[h["run"]].update(
                {"ts": h.get("ts"), "config": h.get("config") or {}, "dataset": h.get("dataset") or [],
                 "dataset_folder": h.get("dataset_folder") or "dataset", "note": h.get("note")}
            )
        elif h.get("event") == "train_end" and h.get("run"):
            runs.setdefault(h["run"], {})
            runs[h["run"]].update({"end_ts": h.get("ts"), "status": h.get("status"), "checkpoints": h.get("checkpoints") or [],
                                   "duration_min": h.get("duration_min")})
    nodes: list[dict] = []
    edges: list[dict] = []  # 副次エッジ（点線）
    has_dataset = any(i["folder"] == "dataset" or i["folder"].startswith("dataset/") or (i["meta"] or {}).get("stage") == "dataset" for i in items)
    nodes.append({"id": "base", "type": "base", "label": "Krea 2 Turbo", "parent": None, "ts": 0})
    if has_dataset or runs:
        nodes.append({"id": "dataset", "type": "dsgroup", "label": "素材", "parent": None, "ts": 0})

    def ensure_run(name: str):
        rid = "run:" + name
        if not any(n["id"] == rid for n in nodes):
            r = runs.get(name, {})
            nodes.append({"id": rid, "type": "run", "run": name, "label": name, "parent": "dataset" if ("dataset" in {n["id"] for n in nodes}) else "base",
                          "ts": r.get("ts") or "", "config": r.get("config") or {}, "status": r.get("status"),
                          "checkpoints": r.get("checkpoints") or [], "duration_min": r.get("duration_min"), "note": r.get("note"),
                          "dataset_count": len(r.get("dataset") or []), "recorded": bool(r)})
        return rid

    for name in runs:
        ensure_run(name)

    gens_so_far: list[dict] = []
    for it in items:
        m = it["meta"] or {}
        is_ds = it["folder"] == "dataset" or it["folder"].startswith("dataset/") or m.get("stage") == "dataset"
        nid = "img:" + it["path"]
        explicit = m.get("parent") if m.get("parent") in by_path and m.get("parent") != it["path"] else None
        node = {"id": nid, "type": "dataset" if is_ds else "gen", "path": it["path"], "folder": it["folder"], "name": it["name"],
                "meta": m, "ts": it["mtime"], "star": it["star"], "parent": None, "inferred": False, "w": it["w"], "h": it["h"]}
        if is_ds:
            node["parent"] = "dataset"
            if explicit:
                edges.append({"from": "img:" + explicit, "to": nid, "kind": "素材化"})
        else:
            run, _step = _run_of(m)
            rid = ensure_run(run) if run else None
            if explicit:
                node["parent"] = "img:" + explicit
                if rid:
                    edges.append({"from": rid, "to": nid, "kind": "LoRA"})
            elif rid:
                node["parent"] = rid
            else:
                best, best_score = None, 0.0
                p = m.get("prompt") or ""
                for cand in gens_so_far[-40:]:
                    cm = cand["meta"] or {}
                    sc = _similarity(cm.get("prompt") or "", p)
                    if cand["folder"] == it["folder"]:
                        sc += 0.08
                    if cm.get("seed") == m.get("seed"):
                        sc += 0.04
                    if sc > best_score:
                        best, best_score = cand, sc
                if best and best_score >= 0.4:
                    node["parent"] = "img:" + best["path"]
                    node["inferred"] = True
                else:
                    node["parent"] = "base"
            gens_so_far.append(it)
        nodes.append(node)
    ids = {n["id"] for n in nodes}
    edges = [e for e in edges if e["from"] in ids and e["to"] in ids]
    return {"nodes": nodes, "edges": edges}


@app.get("/api/graph")
def api_graph():
    return _build_graph()


@app.post("/api/parent/{path:path}")
def api_parent(path: str, body: dict = Body(...)):
    rel = _safe_rel(path).as_posix()
    full = IMAGES / rel
    if not full.exists():
        raise HTTPException(404)
    parent = body.get("parent")
    if parent:
        prel = _safe_rel(parent).as_posix()
        if prel == rel or not (IMAGES / prel).exists():
            raise HTTPException(400, "bad parent")
        parent = prel
    with _lock:
        m = _meta(full)
        old = m.get("parent")
        if parent:
            m["parent"] = parent
        else:
            m.pop("parent", None)
        _write_meta(full, m)
        _append_history({"event": "reparent", "path": rel, "parent": parent, "old_parent": old})
    return {"ok": True, "path": rel, "parent": parent}


# ---------- jobs / worker ----------

JOBS = DATA / "jobs.json"
JOBLOGS = DATA / "jobs"
WORKER = DATA / "worker.json"
JOBLOGS.mkdir(parents=True, exist_ok=True)
JOB_TYPES = {"gen", "train", "compare", "edit"}
# edit は RunPod 中継ワーカー（runpod_worker.py）、それ以外は WSL2 ワーカーが実行する


def _worker_kind(worker: str | None) -> str:
    return "runpod" if (worker or "").startswith("runpod") else "wsl2"


def _job_kind(t: str) -> str:
    return "runpod" if t == "edit" else "wsl2"


def _load_jobs() -> list[dict]:
    if JOBS.exists():
        try:
            return json.loads(JOBS.read_text())
        except Exception:
            return []
    return []


def _save_jobs(jobs: list[dict]) -> None:
    tmp = JOBS.with_suffix(".tmp")
    tmp.write_text(json.dumps(jobs, ensure_ascii=False, indent=1))
    tmp.replace(JOBS)


def _job_public(j: dict, tail: int = 0) -> dict:
    out = dict(j)
    if tail:
        lf = JOBLOGS / f"{j['id']}.log"
        if lf.exists():
            lines = lf.read_text(encoding="utf-8", errors="replace").splitlines()
            out["log"] = lines[-tail:]
        else:
            out["log"] = []
    return out


def _who(request_headers) -> str | None:
    # Tailscale Serve 経由なら誰が操作したかが付く
    return request_headers.get("tailscale-user-login") or request_headers.get("x-tailscale-user-login")


from fastapi import Request


@app.get("/api/jobs")
def api_jobs(limit: int = 50):
    jobs = _load_jobs()
    return {"items": [_job_public(j) for j in reversed(jobs[-limit:])], "total": len(jobs)}


@app.get("/api/jobs/next")
def api_jobs_next(worker: str = "wsl2", authorization: str | None = Header(default=None)):
    _check_token(authorization)
    with _lock:
        jobs = _load_jobs()
        kind = _worker_kind(worker)
        if any(j["status"] == "running" and _worker_kind(j.get("worker")) == kind for j in jobs):
            return {"job": None, "reason": "another job is running"}
        for j in jobs:
            if j["status"] == "queued" and _job_kind(j["type"]) == kind:
                j.update({"status": "running", "started_at": _now(), "worker": worker, "progress": {}})
                _save_jobs(jobs)
                return {"job": j}
    return {"job": None}


@app.get("/api/jobs/{job_id}")
def api_job(job_id: str, tail: int = 200):
    for j in _load_jobs():
        if j["id"] == job_id:
            return _job_public(j, tail)
    raise HTTPException(404)


@app.post("/api/jobs")
def api_job_create(request: Request, body: dict = Body(...)):
    t = body.get("type")
    if t not in JOB_TYPES:
        raise HTTPException(400, f"type must be one of {sorted(JOB_TYPES)}")
    params = body.get("params") or {}
    if t == "gen" and not (params.get("prompt") or "").strip():
        raise HTTPException(400, "prompt required")
    if t == "train" and not re.match(r"^[A-Za-z0-9_.-]+$", params.get("run") or ""):
        raise HTTPException(400, "run name required ([A-Za-z0-9_.-])")
    if t == "compare" and not (params.get("run") and (params.get("prompt") or "").strip()):
        raise HTTPException(400, "run and prompt required")
    if t == "edit":
        # 先頭は必ずギャラリー上の画像。以降は ギャラリー上のパス か、Pod 上の絶対パス（/workspace/... は Pod にある前提で通す）
        ctrl = [str(c).strip() if str(c).strip().startswith("/") else str(c).strip().strip("/")
                for c in (params.get("control") or []) if str(c).strip()]
        if not (params.get("prompt") or "").strip() or not ctrl:
            raise HTTPException(400, "prompt and control image required")
        if ctrl[0].startswith("/"):
            raise HTTPException(400, "first control image must be a gallery path")
        for c in ctrl:
            if not c.startswith("/") and not (IMAGES / c).is_file():
                raise HTTPException(400, f"image not found: {c}")
        params["control"] = ctrl
    with _lock:
        jobs = _load_jobs()
        jid = time.strftime("%Y%m%d-%H%M%S") + f"-{len(jobs) + 1:04d}"
        job = {"id": jid, "type": t, "params": params, "note": body.get("note") or None, "status": "queued",
               "created_at": _now(), "by": _who(request.headers), "progress": {}, "cancel": False}
        jobs.append(job)
        _save_jobs(jobs)
        _append_history({"event": "job_queued", "job": jid, "type": t, "params": params, "note": job["note"], "by": job["by"]})
    return {"ok": True, "job": job}


@app.post("/api/jobs/{job_id}/cancel")
def api_job_cancel(job_id: str):
    with _lock:
        jobs = _load_jobs()
        for j in jobs:
            if j["id"] == job_id:
                if j["status"] == "queued":
                    j.update({"status": "cancelled", "finished_at": _now()})
                elif j["status"] == "running":
                    j["cancel"] = True
                else:
                    raise HTTPException(400, "not cancellable")
                _save_jobs(jobs)
                return {"ok": True, "job": j}
    raise HTTPException(404)


@app.post("/api/jobs/{job_id}/log")
def api_job_log(job_id: str, body: dict = Body(...), authorization: str | None = Header(default=None)):
    _check_token(authorization)
    lines = body.get("lines") or []
    if lines:
        with (JOBLOGS / f"{job_id}.log").open("a", encoding="utf-8") as f:
            for ln in lines:
                f.write(str(ln).rstrip("\n") + "\n")
    with _lock:
        jobs = _load_jobs()
        for j in jobs:
            if j["id"] == job_id:
                if body.get("progress"):
                    j["progress"] = {**(j.get("progress") or {}), **body["progress"], "updated_at": _now()}
                    # loss の履歴（最大 600 点）
                    if "loss" in body["progress"] and body["progress"].get("step") is not None:
                        hist = j.setdefault("loss_history", [])
                        if not hist or hist[-1][0] != body["progress"]["step"]:
                            hist.append([body["progress"]["step"], body["progress"]["loss"]])
                            if len(hist) > 600:
                                j["loss_history"] = hist[::2]
                _save_jobs(jobs)
                return {"ok": True, "cancel": bool(j.get("cancel"))}
    raise HTTPException(404)


@app.post("/api/jobs/{job_id}/finish")
def api_job_finish(job_id: str, body: dict = Body(...), authorization: str | None = Header(default=None)):
    _check_token(authorization)
    status = body.get("status") or "done"
    with _lock:
        jobs = _load_jobs()
        for j in jobs:
            if j["id"] == job_id:
                j.update({"status": status, "finished_at": _now(), "result": body.get("result") or {}})
                _save_jobs(jobs)
                _append_history({"event": "job_" + status, "job": job_id, "type": j["type"], "result": j["result"]})
                return {"ok": True}
    raise HTTPException(404)


@app.post("/api/worker/heartbeat")
def api_worker_heartbeat(body: dict = Body(...), authorization: str | None = Header(default=None)):
    _check_token(authorization)
    body["ts"] = _now()
    WORKER.write_text(json.dumps(body, ensure_ascii=False))
    return {"ok": True}


@app.get("/api/worker")
def api_worker():
    if not WORKER.exists():
        return {"online": False}
    try:
        w = json.loads(WORKER.read_text())
    except Exception:
        return {"online": False}
    age = time.time() - time.mktime(time.strptime(w.get("ts", "1970-01-01T00:00:00"), "%Y-%m-%dT%H:%M:%S"))
    w["age_sec"] = int(age)
    w["online"] = age < 90
    return w


@app.get("/api/health")
def api_health():
    return {"ok": True}


@app.get("/api/me")
def api_me(request: Request):
    return {"user": _who(request.headers)}


# ---------- PWA ----------

from fastapi.responses import Response


@app.get("/manifest.webmanifest")
def manifest():
    return JSONResponse(
        {"name": "Krea2 Gallery", "short_name": "Krea2", "start_url": "/", "display": "standalone",
         "background_color": "#0f1115", "theme_color": "#171a21",
         "icons": [{"src": "/icons/icon-192.png", "sizes": "192x192", "type": "image/png"},
                   {"src": "/icons/icon-512.png", "sizes": "512x512", "type": "image/png"}]},
        media_type="application/manifest+json",
    )


_icon_cache: dict[int, bytes] = {}


def _icon(size: int) -> bytes:
    if size not in _icon_cache:
        from PIL import ImageDraw
        im = Image.new("RGB", (size, size), "#171a21")
        d = ImageDraw.Draw(im)
        m = size // 8
        d.rounded_rectangle([m, m, size - m, size - m], radius=size // 6, fill="#f5b940")
        # パンダ風の丸耳 + 顔
        r = size // 7
        d.ellipse([size * 0.28 - r, size * 0.32 - r, size * 0.28 + r, size * 0.32 + r], fill="#0f1115")
        d.ellipse([size * 0.72 - r, size * 0.32 - r, size * 0.72 + r, size * 0.32 + r], fill="#0f1115")
        d.ellipse([size * 0.22, size * 0.30, size * 0.78, size * 0.80], fill="#ffffff")
        e = size // 12
        d.ellipse([size * 0.38 - e, size * 0.52 - e, size * 0.38 + e, size * 0.52 + e], fill="#0f1115")
        d.ellipse([size * 0.62 - e, size * 0.52 - e, size * 0.62 + e, size * 0.52 + e], fill="#0f1115")
        import io
        buf = io.BytesIO()
        im.save(buf, "PNG")
        _icon_cache[size] = buf.getvalue()
    return _icon_cache[size]


ICONS = STATIC / "icons"


@app.get("/icons/icon-{size}.png")
def icon(size: int):
    f = ICONS / f"icon-{size}.png"
    if f.exists():
        return FileResponse(f, media_type="image/png")
    if size not in (180, 192, 512):
        raise HTTPException(404)
    return Response(_icon(size), media_type="image/png")


@app.get("/apple-touch-icon.png")
def apple_icon():
    f = ICONS / "icon-180.png"
    return FileResponse(f, media_type="image/png") if f.exists() else Response(_icon(180), media_type="image/png")


@app.get("/favicon.ico")
def favicon():
    f = ICONS / "favicon.ico"
    if not f.exists():
        raise HTTPException(404)
    return FileResponse(f, media_type="image/x-icon")


@app.get("/healthz")
def healthz():
    return JSONResponse({"ok": True})


_backfill_history()
