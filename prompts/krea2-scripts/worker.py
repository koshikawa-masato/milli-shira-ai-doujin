#!/usr/bin/env python3
"""Krea2 ワーカー（WSL2 常駐）

Pi5 のギャラリー（Tailscale 経由 HTTPS）からジョブを取りに行き、gen.sh / train.sh / compare.sh を実行し、
進捗（step / loss / ETA）とログを送り返す。Pi5 → WSL2 の SSH は不要（pull 型）。

設定: ~/krea2/.gallery_env の GALLERY_URL / GALLERY_TOKEN
起動: systemctl --user start krea2-worker   （prompts/krea2-scripts/krea2-worker.service）
"""
from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HOME = Path.home()
KREA = HOME / "krea2"
SCRIPTS = KREA / "scripts"
ENV_FILE = KREA / ".gallery_env"
NVSMI = "/usr/lib/wsl/lib/nvidia-smi"
WORKER_NAME = os.environ.get("WORKER_NAME", "wsl2")
POLL = 5
HEARTBEAT = 20


def load_env() -> tuple[str, str]:
    url = token = ""
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if line.startswith("GALLERY_URL="):
            url = line.split("=", 1)[1].strip().strip('"')
        elif line.startswith("GALLERY_TOKEN="):
            token = line.split("=", 1)[1].strip().strip('"')
    if not url or not token:
        sys.exit(f"GALLERY_URL / GALLERY_TOKEN not set in {ENV_FILE}")
    return url.rstrip("/"), token


URL, TOKEN = load_env()


def api(method: str, path: str, body: dict | None = None, timeout: int = 20, retries: int = 1) -> dict:
    """retries 回まで再試行（サーバ再起動中の 502 などを吸収）。"""
    data = json.dumps(body).encode() if body is not None else None
    last: Exception | None = None
    for i in range(retries):
        try:
            req = urllib.request.Request(URL + path, data=data, method=method,
                                         headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode() or "{}")
        except Exception as e:  # noqa: BLE001
            last = e
            if i < retries - 1:
                time.sleep(min(30, 3 * (i + 1)))
    assert last is not None
    raise last


def gpu_info() -> dict:
    try:
        out = subprocess.run([NVSMI, "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu",
                              "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=10).stdout.strip()
        name, util, used, total, temp = [x.strip() for x in out.split(",")]
        return {"name": name, "util": int(util), "mem_used": int(used), "mem_total": int(total), "temp": int(temp)}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


def loras() -> list[str]:
    return sorted(str(p) for p in (KREA / "output").glob("*.safetensors"))


def dataset_count() -> int:
    d = KREA / "dataset" / "images"
    return len([p for p in d.glob("*") if p.suffix.lower() in (".png", ".jpg", ".jpeg")]) if d.exists() else 0


def heartbeat(running: str | None) -> None:
    try:
        api("POST", "/api/worker/heartbeat", {"worker": WORKER_NAME, "gpu": gpu_info(), "loras": loras(),
                                               "dataset_count": dataset_count(), "running": running})
    except Exception as e:  # noqa: BLE001
        log(f"heartbeat failed: {e}")


def log(msg: str) -> None:
    print(time.strftime("%H:%M:%S"), msg, flush=True)


# ---- 進捗パース ----
_step_re = re.compile(r"(\d+)/(\d+)\s*\[([^\]]*)\]")          # tqdm: 220/1800 [03:20<23:56,  1.10it/s, avr_loss=0.41]
_loss_re = re.compile(r"avr_loss=([\d.]+)")
_phase_re = re.compile(r"^(steps|sampling|Loading [^:]+|== [^=]+ ==|INFO:[^:]+:(.*))")


def parse_progress(line: str, cur: dict) -> dict | None:
    p = {}
    m = _step_re.search(line)
    if m:
        p["step"], p["total"] = int(m.group(1)), int(m.group(2))
        inner = m.group(3)
        mm = re.search(r"<([\d:]+)", inner)
        if mm:
            p["eta"] = mm.group(1)
        mr = re.search(r"([\d.]+(?:it/s|s/it))", inner)
        if mr:
            p["rate"] = mr.group(1)
    ml = _loss_re.search(line)
    if ml:
        p["loss"] = float(ml.group(1))
    if line.startswith("steps:"):
        p["phase"] = "学習"
    elif line.startswith("sampling:"):
        p["phase"] = "生成"
    elif line.startswith("Loading"):
        p["phase"] = "モデル読込"
    elif line.startswith("== "):
        p["phase"] = line.strip("= ").strip()
    elif "cache" in line.lower() and "==" in line:
        p["phase"] = "キャッシュ"
    return p or None


# ---- ジョブ実行 ----
def build_cmd(job: dict) -> tuple[list[str], dict]:
    t, p = job["type"], job.get("params") or {}
    env = os.environ.copy()
    env["PATH"] = env.get("PATH", "") + ":/usr/lib/wsl/lib"
    if job.get("note"):
        env["NOTE"] = str(job["note"])
    if t == "gen":
        if p.get("parent"):
            env["PARENT"] = str(p["parent"])
        folder = re.sub(r"[^A-Za-z0-9_./-]", "_", str(p.get("folder") or "test")).strip("/") or "test"
        out = str(KREA / "output" / folder)
        count = max(1, min(int(p.get("count") or 1), 8))
        seed0 = int(p.get("seed") or 0)
        lora = str(p.get("lora") or "")
        if lora and not Path(lora).exists():
            raise FileNotFoundError(f"LoRA not found: {lora}")
        if p.get("lora_multiplier") not in (None, ""):
            env["LORA_MULTIPLIER"] = str(float(p["lora_multiplier"]))
        # 複数枚は seed を +1 ずつ
        parts = " && ".join(
            f'{SCRIPTS}/gen.sh "$PROMPT" {seed0 + i} "$LORA" "$OUT"' for i in range(count))
        env.update({"PROMPT": str(p["prompt"]), "LORA": lora, "OUT": out})
        return ["bash", "-c", parts], env
    if t == "train":
        run = re.sub(r"[^A-Za-z0-9_.-]", "", str(p["run"]))
        args = [str(SCRIPTS / "train.sh"), run, str(int(p.get("steps") or 1800)), str(int(p.get("save_every") or 300)),
                str(int(p.get("dim") or 32)), str(p.get("lr") or "1e-4"), str(int(p.get("swap") or 16)), str(job.get("note") or "")]
        cmd = " ".join(f"'{a}'" for a in args)
        if (p.get("compare_prompt") or "").strip():
            cp = str(p["compare_prompt"]).replace("'", "'\\''")
            cmd += f" && '{SCRIPTS}/compare.sh' '{run}' '{cp}' {int(p.get('compare_seed') or 0)}"
        return ["bash", "-c", cmd], env
    if t == "compare":
        run = re.sub(r"[^A-Za-z0-9_.-]", "", str(p["run"]))
        args = [str(SCRIPTS / "compare.sh"), run, str(p["prompt"]), str(int(p.get("seed") or 0))]
        if (p.get("steps") or "").strip():
            args.append(re.sub(r"[^0-9 ]", "", str(p["steps"])))
        return args, env
    raise ValueError(f"unknown job type {t}")


def run_job(job: dict) -> None:
    jid = job["id"]
    log(f"job {jid} start: {job['type']}")
    buf: list[str] = []
    progress: dict = {}
    last_flush = 0.0
    last_hb = 0.0
    cancel = False

    def flush(force=False):
        nonlocal buf, last_flush, progress, cancel
        if not force and time.time() - last_flush < 2:
            return
        try:
            r = api("POST", f"/api/jobs/{jid}/log", {"lines": buf[-200:], "progress": progress or None}, retries=3)
            cancel = cancel or bool(r.get("cancel"))
        except Exception as e:  # noqa: BLE001
            log(f"log post failed: {e}")
        buf = []
        progress = {}
        last_flush = time.time()

    try:
        cmd, env = build_cmd(job)
    except Exception as e:  # noqa: BLE001
        api("POST", f"/api/jobs/{jid}/log", {"lines": [f"ERROR: {e}"]}, retries=3)
        api("POST", f"/api/jobs/{jid}/finish", {"status": "failed", "result": {"summary": str(e)}}, retries=10)
        return
    buf.append("$ " + (cmd[-1] if cmd[0] == "bash" else " ".join(cmd)))
    proc = subprocess.Popen(cmd, env=env, cwd=str(KREA), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            start_new_session=True)
    assert proc.stdout
    partial = b""
    status = "done"
    summary = ""
    saved: list[str] = []
    while True:
        chunk = proc.stdout.read1(4096) if hasattr(proc.stdout, "read1") else proc.stdout.read(4096)
        if not chunk:
            break
        partial += chunk
        # tqdm は \r 区切りなので \r と \n 両方で切る
        while True:
            idx_n, idx_r = partial.find(b"\n"), partial.find(b"\r")
            idxs = [i for i in (idx_n, idx_r) if i >= 0]
            if not idxs:
                break
            i = min(idxs)
            line = partial[:i].decode("utf-8", "replace").strip()
            partial = partial[i + 1:]
            if not line:
                continue
            pr = parse_progress(line, progress)
            if pr:
                progress.update(pr)
                # tqdm の進捗行は最新だけ残す
                if buf and re.match(r"^(steps|sampling|Loading)", buf[-1]) and re.match(r"^(steps|sampling|Loading)", line):
                    buf[-1] = line
                else:
                    buf.append(line)
            else:
                buf.append(line)
            if line.startswith("saved:"):
                saved.append(line.split(":", 1)[1].strip())
        flush()
        if time.time() - last_hb > HEARTBEAT:
            heartbeat(jid)
            last_hb = time.time()
        if cancel:
            log(f"job {jid} cancel requested")
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            status = "cancelled"
            try:
                proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
            break
    rc = proc.wait()
    if partial.strip():
        buf.append(partial.decode("utf-8", "replace").strip())
    if status != "cancelled":
        status = "done" if rc == 0 else "failed"
    if job["type"] == "gen":
        summary = f"{len(saved)} 枚生成"
    elif job["type"] == "train":
        summary = f"exit {rc}"
    buf.append(f"[exit {rc}] {status}")
    flush(force=True)
    try:
        api("POST", f"/api/jobs/{jid}/finish", {"status": status, "result": {"summary": summary, "saved": saved[-20:], "rc": rc}}, retries=10)
    except Exception as e:  # noqa: BLE001
        log(f"finish post failed: {e}")
    log(f"job {jid} {status} (rc={rc})")


def main() -> None:
    log(f"worker {WORKER_NAME} -> {URL}")
    last_hb = 0.0
    while True:
        if time.time() - last_hb > HEARTBEAT:
            heartbeat(None)
            last_hb = time.time()
        try:
            r = api("GET", f"/api/jobs/next?worker={WORKER_NAME}")
            job = r.get("job")
        except urllib.error.URLError as e:
            log(f"poll failed: {e}")
            job = None
            time.sleep(POLL * 3)
            continue
        except Exception as e:  # noqa: BLE001
            log(f"poll error: {e}")
            job = None
        if job:
            try:
                run_job(job)
            except Exception as e:  # noqa: BLE001
                log(f"job crashed: {e}")
                try:
                    api("POST", f"/api/jobs/{job['id']}/finish", {"status": "failed", "result": {"summary": f"worker error: {e}"}})
                except Exception:
                    pass
            heartbeat(None)
            last_hb = time.time()
        else:
            time.sleep(POLL)


if __name__ == "__main__":
    main()
