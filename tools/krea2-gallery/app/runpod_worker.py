"""RunPod Serverless 中継ワーカー（Pi5 のギャラリー横で動く）
ギャラリーのジョブキューから type=edit を取り、RunPod の編集エンドポイントへ投げ、結果画像をギャラリーに登録する。
Pod/Serverless は tailnet 外で Pi5 に届かないので、Pi5 側から取りに行く形にしている。
環境変数: RUNPOD_API_KEY, RUNPOD_ENDPOINT_ID（無ければ待機だけする）, GALLERY_URL（既定 http://gallery:8020）, GALLERY_TOKEN
"""
from __future__ import annotations

import base64
import io
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid

API_KEY = os.environ.get("RUNPOD_API_KEY", "").strip()
ENDPOINT = os.environ.get("RUNPOD_ENDPOINT_ID", "").strip()
GALLERY = os.environ.get("GALLERY_URL", "http://gallery:8020").rstrip("/")
TOKEN = os.environ.get("GALLERY_TOKEN", "")
WORKER = "runpod-serverless"
POLL = 10


def log(msg: str) -> None:
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def http(url: str, method: str = "GET", body: bytes | None = None, headers: dict | None = None, timeout: int = 60) -> dict:
    req = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode() or "{}")


def gallery(path: str, method: str = "GET", body: dict | None = None) -> dict:
    h = {"Authorization": f"Bearer {TOKEN}"}
    data = None
    if body is not None:
        h["Content-Type"] = "application/json"
        data = json.dumps(body, ensure_ascii=False).encode()
    return http(f"{GALLERY}{path}", method, data, h)


def runpod(path: str, body: dict | None = None) -> dict:
    h = {"Authorization": f"Bearer {API_KEY}"}
    data = None
    if body is not None:
        h["Content-Type"] = "application/json"
        data = json.dumps(body).encode()
    return http(f"https://api.runpod.ai/v2/{ENDPOINT}/{path}", "POST" if body is not None else "GET", data, h, timeout=120)


def fetch_image_b64(path: str) -> str:
    req = urllib.request.Request(f"{GALLERY}/img/{urllib.request.quote(path)}")
    with urllib.request.urlopen(req, timeout=60) as r:
        return base64.b64encode(r.read()).decode()


def upload(png: bytes, folder: str, meta: dict) -> dict:
    boundary = "----krea2" + uuid.uuid4().hex
    name = time.strftime("%Y%m%d-%H%M%S") + f"-{uuid.uuid4().hex[:3]}_{meta.get('seed', 0)}.png"
    parts = io.BytesIO()

    def field(k: str, v: str) -> None:
        parts.write(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode())

    field("folder", folder)
    field("meta", json.dumps(meta, ensure_ascii=False))
    parts.write(f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{name}\"\r\nContent-Type: image/png\r\n\r\n".encode())
    parts.write(png)
    parts.write(f"\r\n--{boundary}--\r\n".encode())
    return http(f"{GALLERY}/api/upload", "POST", parts.getvalue(),
                {"Authorization": f"Bearer {TOKEN}", "Content-Type": f"multipart/form-data; boundary={boundary}"}, timeout=120)


def job_log(jid: str, lines: list[str], progress: dict | None = None) -> None:
    try:
        gallery(f"/api/jobs/{jid}/log", "POST", {"lines": lines, "progress": progress or {}})
    except Exception as e:  # ログ失敗で止めない
        log(f"log failed: {e}")


def finish(jid: str, status: str, result: dict) -> None:
    gallery(f"/api/jobs/{jid}/finish", "POST", {"status": status, "result": result})


def run_edit(job: dict) -> None:
    jid, p = job["id"], job.get("params") or {}
    control = [c for c in (p.get("control") or []) if c]
    folder = str(p.get("folder") or "edit").strip("/") or "edit"
    payload = {"prompt": p["prompt"], "control": [fetch_image_b64(c) for c in control],
               "seed": int(p.get("seed") or 0), "width": int(p.get("width") or 1024), "height": int(p.get("height") or 1024),
               "steps": int(p.get("steps") or 25), "guidance": float(p.get("guidance") or 4.0)}
    if p.get("negative"):
        payload["negative"] = p["negative"]
    t0 = time.time()
    r = runpod("run", {"input": payload})
    rid = r.get("id")
    job_log(jid, [f"runpod job {rid} submitted ({len(control)} control images, {payload['width']}x{payload['height']})"], {"pct": 1})
    status = r.get("status")
    while status in (None, "IN_QUEUE", "IN_PROGRESS"):
        time.sleep(POLL)
        try:
            j = gallery(f"/api/jobs/{jid}?tail=0")
            if j.get("cancel"):
                runpod(f"cancel/{rid}", {})
                finish(jid, "cancelled", {"runpod_id": rid})
                return
        except Exception:
            pass
        r = runpod(f"status/{rid}")
        status = r.get("status")
        el = int(time.time() - t0)
        job_log(jid, [f"{status} {el}s"], {"pct": 5 if status == "IN_QUEUE" else 50, "elapsed": el})
    if status != "COMPLETED":
        finish(jid, "failed", {"runpod_id": rid, "status": status, "error": r.get("error")})
        job_log(jid, [f"failed: {status} {r.get('error')}"])
        return
    out = r.get("output") or {}
    if "error" in out or not out.get("image"):
        finish(jid, "failed", {"runpod_id": rid, "error": out.get("error", "no image")})
        job_log(jid, [f"failed: {out.get('error', 'no image')}"])
        return
    png = base64.b64decode(out["image"])
    meta = {"stage": "gen", "tool": "qwen-image-edit-2511", "prompt": p["prompt"], "seed": out.get("seed", payload["seed"]),
            "parent": control[0], "control": control[0], "refs": control[1:] or None,
            "steps": payload["steps"], "guidance_scale": payload["guidance"], "note": job.get("note") or None,
            "worker": WORKER, "runpod_id": rid, "elapsed_sec": out.get("elapsed_sec"), "job": jid}
    up = upload(png, folder, meta)
    job_log(jid, [f"saved: {up.get('path')} (worker {out.get('elapsed_sec')}s, total {int(time.time() - t0)}s)"], {"pct": 100})
    finish(jid, "done", {"path": up.get("path"), "runpod_id": rid, "elapsed_sec": int(time.time() - t0)})


def main() -> None:
    if not API_KEY or not ENDPOINT:
        log("RUNPOD_API_KEY / RUNPOD_ENDPOINT_ID が未設定。.env に入れるまで待機します")
        while True:
            time.sleep(3600)
    log(f"runpod worker up: endpoint {ENDPOINT}, gallery {GALLERY}")
    while True:
        try:
            r = gallery("/api/jobs/next?worker=runpod")
            job = r.get("job")
            if job:
                log(f"job {job['id']} {job['type']}")
                try:
                    if job["type"] == "edit":
                        run_edit(job)
                    else:
                        finish(job["id"], "failed", {"error": f"unsupported type {job['type']}"})
                except Exception as e:
                    log(f"job {job['id']} error: {e}")
                    try:
                        finish(job["id"], "failed", {"error": str(e)})
                    except Exception:
                        pass
                continue
        except urllib.error.URLError as e:
            log(f"gallery unreachable: {e}")
        except Exception as e:
            log(f"loop error: {e}")
        time.sleep(POLL)


if __name__ == "__main__":
    sys.exit(main())
