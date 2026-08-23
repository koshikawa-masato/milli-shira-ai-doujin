"""RunPod 中継ワーカー（Pi5 のギャラリー横で動く）
ギャラリーのジョブキューから RunPod 向けのジョブ（type=edit）を取り、RunPod で実行して結果をギャラリーに登録する。
Pod/Serverless は tailnet 外で Pi5 に届かないので、Pi5 側から取りに行く／送り込む形にしている。

モード（環境変数で切替）:
  Pod モード      RUNPOD_POD_ID を設定。ジョブが来たら Pod を起動 → ssh で edit_batch.sh を実行 → 結果を scp で回収 →
                  キューが空になったら Pod を停止（RUNPOD_IDLE_STOP_SEC 秒待ってから。既定 0 = 即停止）
  Serverless モード RUNPOD_ENDPOINT_ID を設定。api.runpod.ai の /run に投げて /status を待つ
共通: RUNPOD_API_KEY, GALLERY_URL（既定 http://gallery:8020）, GALLERY_TOKEN
Pod モードの ssh 鍵: RUNPOD_SSH_KEY（既定 /root/.ssh/keys/id_ed25519。compose で ./ssh を読み取り専用マウント）
"""
from __future__ import annotations

import base64
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

API_KEY = os.environ.get("RUNPOD_API_KEY", "").strip()
ENDPOINT = os.environ.get("RUNPOD_ENDPOINT_ID", "").strip()
POD_ID = os.environ.get("RUNPOD_POD_ID", "").strip()
IDLE_STOP = int(os.environ.get("RUNPOD_IDLE_STOP_SEC", "0") or 0)
SSH_KEY = os.environ.get("RUNPOD_SSH_KEY", "/root/.ssh/keys/id_ed25519")
GALLERY = os.environ.get("GALLERY_URL", "http://gallery:8020").rstrip("/")
TOKEN = os.environ.get("GALLERY_TOKEN", "")
POD_ROOT = "/workspace/krea2"
POLL = 10
MODE = "pod" if POD_ID else ("serverless" if ENDPOINT else "")
WORKER = f"runpod-{MODE}"


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


def fetch_image(path: str) -> bytes:
    with urllib.request.urlopen(f"{GALLERY}/img/{urllib.parse.quote(path)}", timeout=60) as r:
        return r.read()


def upload(png: bytes, folder: str, meta: dict, name: str | None = None) -> dict:
    boundary = "----krea2" + uuid.uuid4().hex
    name = name or time.strftime("%Y%m%d-%H%M%S") + f"-{uuid.uuid4().hex[:3]}_{meta.get('seed', 0)}.png"
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


def heartbeat(running: str | None, extra: dict | None = None) -> None:
    try:
        gallery("/api/worker/heartbeat", "POST", {"worker": WORKER, "running": running, **(extra or {})})
    except Exception:
        pass


def cancelled(jid: str) -> bool:
    try:
        return bool(gallery(f"/api/jobs/{jid}?tail=0").get("cancel"))
    except Exception:
        return False


def queued_for_runpod() -> int:
    try:
        return sum(1 for j in gallery("/api/jobs?limit=200").get("items", []) if j.get("status") == "queued" and j.get("type") == "edit")
    except Exception:
        return 0


# ---------------- RunPod REST ----------------
def rp_api(path: str, method: str = "GET", body: dict | None = None) -> dict:
    h = {"Authorization": f"Bearer {API_KEY}"}
    data = None
    if body is not None:
        h["Content-Type"] = "application/json"
        data = json.dumps(body).encode()
    return http(f"https://api.runpod.io{path}", method, data, h, timeout=60)


def rp_serverless(path: str, body: dict | None = None) -> dict:
    h = {"Authorization": f"Bearer {API_KEY}"}
    data = None
    if body is not None:
        h["Content-Type"] = "application/json"
        data = json.dumps(body).encode()
    return http(f"https://api.runpod.ai/v2/{ENDPOINT}/{path}", "POST" if body is not None else "GET", data, h, timeout=120)


# ---------------- Pod モード ----------------
class Pod:
    def __init__(self) -> None:
        self.host = self.port = None

    def info(self) -> dict:
        return rp_api(f"/v2/pods/{POD_ID}")

    def ssh_base(self) -> list[str]:
        return ["ssh", "-i", SSH_KEY, "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null",
                "-o", "LogLevel=ERROR", "-o", "ConnectTimeout=20", "-o", "ServerAliveInterval=30", "-p", str(self.port)]

    def ssh(self, cmd: str, timeout: int = 120) -> subprocess.CompletedProcess:
        return subprocess.run(self.ssh_base() + [f"root@{self.host}", cmd], capture_output=True, text=True, timeout=timeout)

    def scp(self, src: str, dst: str, to_pod: bool = True, timeout: int = 600) -> None:
        base = ["scp", "-q", "-i", SSH_KEY, "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null",
                "-o", "LogLevel=ERROR", "-P", str(self.port)]
        args = base + ([src, f"root@{self.host}:{dst}"] if to_pod else [f"root@{self.host}:{src}", dst])
        subprocess.run(args, check=True, timeout=timeout)

    def ensure_running(self, jid: str) -> None:
        """停止中なら起動し、ssh が通るまで待つ。起動ごとに公開ポートが変わるので毎回 API から取る"""
        p = self.info()
        st = p.get("status")
        if st != "RUNNING":
            job_log(jid, [f"pod {POD_ID} is {st}: starting"], {"pct": 1})
            rp_api(f"/v2/pods/{POD_ID}/action", "POST", {"action": "start"})
            for _ in range(60):
                time.sleep(10)
                p = self.info()
                if p.get("status") == "RUNNING":
                    break
            else:
                raise RuntimeError(f"pod did not reach RUNNING (last {p.get('status')})")
        d = ((p.get("ssh") or {}).get("direct") or {})
        self.host, self.port = d.get("host"), d.get("port")
        if not self.host:
            # runtime.ports から 22/tcp を探す
            for pt in ((p.get("runtime") or {}).get("ports") or []):
                if pt.get("private") == 22 and pt.get("type") == "tcp":
                    self.host, self.port = pt["ip"], pt["public"]
        if not self.host:
            raise RuntimeError("pod has no public ssh port")
        for i in range(30):
            r = self.ssh(f"bash {POD_ROOT}/scripts/pod_boot.sh", timeout=180)
            if r.returncode == 0 and "BOOT_OK" in r.stdout:
                job_log(jid, [f"pod ready: {r.stdout.strip()} ({self.host}:{self.port})"], {"pct": 2})
                return
            time.sleep(10)
        raise RuntimeError("ssh to pod failed after start")

    def stop(self) -> None:
        try:
            rp_api(f"/v2/pods/{POD_ID}/action", "POST", {"action": "stop"})
            log("pod stopped")
        except Exception as e:
            log(f"pod stop failed: {e}")


def run_edit_on_pod(pod: Pod, job: dict) -> None:
    jid, p = job["id"], job.get("params") or {}
    control = [c for c in (p.get("control") or []) if c]
    folder = re.sub(r"[^A-Za-z0-9_./-]", "_", str(p.get("folder") or "edit")).strip("/") or "edit"
    pod.ensure_running(jid)
    # 参照画像を Pod へ（ギャラリー上のパスは送る。/workspace... の絶対パスは Pod 上にあるものとして使う）
    remote_dir = f"{POD_ROOT}/incoming/{jid}"
    pod.ssh(f"mkdir -p {remote_dir}")
    ctrl_remote = []
    with tempfile.TemporaryDirectory() as td:
        for i, c in enumerate(control):
            if c.startswith("/"):
                ctrl_remote.append(c)
                continue
            local = os.path.join(td, f"ctrl_{i}.png")
            with open(local, "wb") as fh:
                fh.write(fetch_image(c))
            pod.scp(local, f"{remote_dir}/ctrl_{i}.png")
            ctrl_remote.append(f"{remote_dir}/ctrl_{i}.png")
        jobs_file = os.path.join(td, "jobs.jsonl")
        with open(jobs_file, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"prompt": p["prompt"], "control": ctrl_remote, "seed": int(p.get("seed") or 0),
                                 "note": job.get("note") or "", "negative": p.get("negative") or None}, ensure_ascii=False) + "\n")
        pod.scp(jobs_file, f"{remote_dir}/jobs.jsonl")
    w, h = int(p.get("width") or 1024), int(p.get("height") or 1024)
    env = (f'SIZE="{h} {w}" FP8=0 TE_CPU=0 BLOCKS_TO_SWAP=0 STEPS={int(p.get("steps") or 25)} '
           f'GUIDANCE={float(p.get("guidance") or 4.0)}')
    cmd = f"cd {POD_ROOT} && {env} {POD_ROOT}/scripts/edit_batch.sh {remote_dir}/jobs.jsonl {POD_ROOT}/output/{folder} 2>&1"
    job_log(jid, [f"run: {cmd}"], {"pct": 3})
    t0 = time.time()
    proc = subprocess.Popen(pod.ssh_base() + [f"root@{pod.host}", cmd], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    saved, buf, last = [], [], time.time()
    assert proc.stdout is not None
    for raw in proc.stdout:
        for line in raw.replace("\r", "\n").split("\n"):
            line = line.strip()
            if not line:
                continue
            m = re.search(r"Denoising steps:\s*(\d+)%", line)
            if m:
                pct = 5 + int(m.group(1)) * 0.9
                if time.time() - last > 15:
                    job_log(jid, [line[-120:]], {"pct": pct, "elapsed": int(time.time() - t0)})
                    last = time.time()
                continue
            if line.startswith("saved: "):
                saved.append(line[7:].strip())
            if "Loading" in line and "%" in line and time.time() - last < 15:
                continue
            buf.append(line[-200:])
            if len(buf) >= 5 or time.time() - last > 15:
                job_log(jid, buf, {"elapsed": int(time.time() - t0)})
                buf, last = [], time.time()
        if cancelled(jid):
            proc.kill()
            pod.ssh("pkill -f qwen_image_generate_image || true")
            finish(jid, "cancelled", {})
            return
    proc.wait()
    if buf:
        job_log(jid, buf)
    if proc.returncode != 0 or not saved:
        finish(jid, "failed", {"rc": proc.returncode, "error": "no output" if not saved else "edit_batch failed"})
        return
    # 回収して登録
    paths = []
    with tempfile.TemporaryDirectory() as td:
        for rp in saved:
            local = os.path.join(td, os.path.basename(rp))
            pod.scp(rp, local, to_pod=False)
            meta = {}
            try:
                pod.scp(rp + ".json", local + ".json", to_pod=False)
                meta = json.load(open(local + ".json", encoding="utf-8"))
            except Exception:
                pass
            meta.update({"parent": control[0], "control": control[0], "refs": control[1:] or None,
                         "worker": WORKER, "job": jid, "pod": POD_ID})
            up = upload(open(local, "rb").read(), folder, meta, name=os.path.basename(rp))
            paths.append(up.get("path"))
    job_log(jid, [f"saved: {', '.join(map(str, paths))} ({int(time.time() - t0)}s)"], {"pct": 100})
    finish(jid, "done", {"paths": paths, "elapsed_sec": int(time.time() - t0)})


# ---------------- Serverless モード ----------------
def run_edit_serverless(job: dict) -> None:
    jid, p = job["id"], job.get("params") or {}
    control = [c for c in (p.get("control") or []) if c]
    folder = str(p.get("folder") or "edit").strip("/") or "edit"
    payload = {"prompt": p["prompt"], "control": [base64.b64encode(fetch_image(c)).decode() for c in control],
               "seed": int(p.get("seed") or 0), "width": int(p.get("width") or 1024), "height": int(p.get("height") or 1024),
               "steps": int(p.get("steps") or 25), "guidance": float(p.get("guidance") or 4.0)}
    if p.get("negative"):
        payload["negative"] = p["negative"]
    t0 = time.time()
    r = rp_serverless("run", {"input": payload})
    rid = r.get("id")
    job_log(jid, [f"runpod job {rid} submitted ({len(control)} control images, {payload['width']}x{payload['height']})"], {"pct": 1})
    status = r.get("status")
    while status in (None, "IN_QUEUE", "IN_PROGRESS"):
        time.sleep(POLL)
        if cancelled(jid):
            rp_serverless(f"cancel/{rid}", {})
            finish(jid, "cancelled", {"runpod_id": rid})
            return
        r = rp_serverless(f"status/{rid}")
        status = r.get("status")
        el = int(time.time() - t0)
        job_log(jid, [f"{status} {el}s"], {"pct": 5 if status == "IN_QUEUE" else 50, "elapsed": el})
    out = r.get("output") or {}
    if status != "COMPLETED" or "error" in out or not out.get("image"):
        err = out.get("error") or r.get("error") or status
        finish(jid, "failed", {"runpod_id": rid, "status": status, "error": err})
        job_log(jid, [f"failed: {err}"])
        return
    meta = {"stage": "gen", "tool": "qwen-image-edit-2511", "prompt": p["prompt"], "seed": out.get("seed", payload["seed"]),
            "parent": control[0], "control": control[0], "refs": control[1:] or None,
            "steps": payload["steps"], "guidance_scale": payload["guidance"], "note": job.get("note") or None,
            "worker": WORKER, "runpod_id": rid, "elapsed_sec": out.get("elapsed_sec"), "job": jid}
    up = upload(base64.b64decode(out["image"]), folder, meta)
    job_log(jid, [f"saved: {up.get('path')} (worker {out.get('elapsed_sec')}s, total {int(time.time() - t0)}s)"], {"pct": 100})
    finish(jid, "done", {"path": up.get("path"), "runpod_id": rid, "elapsed_sec": int(time.time() - t0)})


# ---------------- main loop ----------------
def main() -> None:
    if not API_KEY or not MODE:
        log("RUNPOD_API_KEY と RUNPOD_POD_ID（Pod モード）または RUNPOD_ENDPOINT_ID（Serverless）が未設定。.env に入れるまで待機します")
        while True:
            time.sleep(3600)
    log(f"runpod worker up: mode={MODE} {POD_ID or ENDPOINT}, gallery {GALLERY}, idle_stop={IDLE_STOP}s")
    pod = Pod() if MODE == "pod" else None
    pod_used = False
    idle_since = None
    while True:
        try:
            r = gallery("/api/jobs/next?worker=runpod")
            job = r.get("job")
            if job:
                idle_since = None
                log(f"job {job['id']} {job['type']}")
                heartbeat(job["id"])
                try:
                    if job["type"] != "edit":
                        finish(job["id"], "failed", {"error": f"unsupported type {job['type']} for runpod worker"})
                    elif pod:
                        pod_used = True
                        run_edit_on_pod(pod, job)
                    else:
                        run_edit_serverless(job)
                except Exception as e:
                    log(f"job {job['id']} error: {e}")
                    try:
                        finish(job["id"], "failed", {"error": str(e)})
                    except Exception:
                        pass
                continue
            # キューが空: Pod モードなら（猶予の後）停止する
            if pod and pod_used:
                idle_since = idle_since or time.time()
                if time.time() - idle_since >= IDLE_STOP and queued_for_runpod() == 0:
                    pod.stop()
                    pod_used = False
                    idle_since = None
        except urllib.error.URLError as e:
            log(f"gallery unreachable: {e}")
        except Exception as e:
            log(f"loop error: {e}")
        time.sleep(POLL)


if __name__ == "__main__":
    sys.exit(main())
