"""Pod 常駐の編集サーバ（Qwen-Image-Edit-2511 / musubi-tuner）
モデル一式を 1 回だけ GPU に読み込み、QUEUE ディレクトリに置かれたジョブ指示 JSON を順に処理する。
Pod 起動直後に pod_boot.sh が tmux で立ち上げ、Pi5 の中継ワーカーがジョブを置いて結果を待つ。

ジョブ指示 <id>.json:
  {"jobs": [{"prompt": "...", "control": ["/abs/path", ...], "seed": 0, "note": "...", "negative": null}],
   "out": "/workspace/krea2/output/<folder>", "size": [H, W], "steps": 25, "guidance": 4.0}
進捗: <id>.log（tqdm の出力もここに流す） 完了: <id>.state に "done <path> <path>..." または "failed <理由>"
サーバの準備完了: QUEUE/server.ready（読込所要秒を書く）
"""
import glob
import json
import os
import sys
import time
import traceback

import torch
from PIL import Image

ROOT = os.environ.get("KREA2_ROOT", "/workspace/krea2")
QUEUE = f"{ROOT}/queue"
M = f"{ROOT}/models"
NEG_DEFAULT = "lowres, blurry, bad anatomy, extra fingers, text, watermark"
os.makedirs(QUEUE, exist_ok=True)
for stale in ("server.ready",):
    try:
        os.remove(f"{QUEUE}/{stale}")
    except OSError:
        pass

from musubi_tuner import qwen_image_generate_image as q  # noqa: E402

T0 = time.time()
sys.argv = ["edit_server",
            "--dit", f"{M}/split_files/diffusion_models/qwen_image_edit_2511_bf16.safetensors",
            "--vae", f"{M}/qwen_image_vae.safetensors",
            "--text_encoder", f"{M}/split_files/text_encoders/qwen_2.5_vl_7b.safetensors",
            "--model_version", "edit-2511", "--attn_mode", "torch", "--resize_control_to_official_size",
            "--image_size", "1024", "1024", "--infer_steps", "25", "--guidance_scale", "4.0",
            "--prompt", "warmup", "--negative_prompt", NEG_DEFAULT, "--save_path", "/tmp"]
ARGS = q.parse_args()
if ARGS.device is None:
    ARGS.device = "cuda" if torch.cuda.is_available() else "cpu"
GEN = q.get_generation_settings(ARGS)
DEVICE = GEN.device
TE = q.load_shared_models(ARGS)
TE["text_encoder"].to(DEVICE)
TE["conds_cache"] = {}
VAE = q.load_vae(ARGS, DEVICE)
VAE.eval()
DIT = q.load_dit_model(ARGS, DEVICE, GEN.dit_weight_dtype)
DIT_SHARED = {"model": DIT}
LOAD_SEC = int(time.time() - T0)
with open(f"{QUEUE}/server.ready", "w") as fh:
    fh.write(f"{LOAD_SEC}\n")
print(f"[edit_server] ready in {LOAD_SEC}s; VRAM {torch.cuda.memory_allocated() / 2**30:.1f} GiB; watching {QUEUE}", flush=True)


def edit_one(job: dict, out: str, size: list, steps: int, guidance: float) -> str:
    args = q.apply_overrides(ARGS, {
        "prompt": job["prompt"], "negative_prompt": job.get("negative") or NEG_DEFAULT,
        "seed": int(job.get("seed") or 0), "infer_steps": steps, "guidance_scale": guidance,
        "control_image_path": job["control"], "image_size_height": int(size[0]), "image_size_width": int(size[1]),
        # official_resize=False なら参照画像を公式サイズ（約1MP）へ縮小せず、出力サイズに合わせる（描き足しで顔の画素を保つ用）
        "resize_control_to_official_size": bool(job.get("official_resize", True)),
        "mask_path": job.get("mask") or None,   # 白=生成する領域、黒=元画像を保つ（インペイント／描き足し）
    })
    VAE.to(DEVICE)  # decode_latent が VAE を CPU に戻すので、毎回 GPU へ
    with torch.no_grad():
        control_latents, control_nps = q.prepare_image_inputs(args, DEVICE, VAE)
        TE["conds_cache"].clear()
        context, context_null = q.prepare_text_inputs(args, control_nps, DEVICE, TE)
        _, latent = q.generate(args, GEN, DIT_SHARED,
                               precomputed_text_data={"context": context, "context_null": context_null,
                                                      "control": (control_latents, control_nps)})
        pixels = q.decode_latent(VAE, latent, DEVICE)
    arr = (pixels[0].permute(1, 2, 0).clamp(0, 1) * 255).round().to(torch.uint8).numpy()
    os.makedirs(out, exist_ok=True)
    name = time.strftime("%Y%m%d-%H%M%S") + f"-{int(time.time() * 1000) % 1000:03d}_{args.seed}__000.png"
    path = os.path.join(out, name)
    Image.fromarray(arr).save(path)
    src = job["control"][0]
    rel = src[len(ROOT) + len("/output/"):] if src.startswith(f"{ROOT}/output/") else src
    meta = {"stage": "gen", "tool": "qwen-image-edit-2511", "prompt": job["prompt"], "seed": args.seed, "parent": rel, "control": rel,
            "refs": job["control"][1:] or None, "steps": steps, "guidance_scale": guidance, "note": job.get("note") or None,
            "server": True}
    with open(path + ".json", "w", encoding="utf-8") as fh:
        json.dump(meta, fh, ensure_ascii=False)
    folder = out[len(ROOT) + len("/output/"):] if out.startswith(f"{ROOT}/output/") else os.path.basename(out)
    with open(f"{ROOT}/output/history.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "event": "gen", "path": path, "folder": folder, "meta": meta},
                            ensure_ascii=False) + "\n")
    return path


def process(spec_path: str) -> None:
    jid = os.path.basename(spec_path)[:-5]
    log_path, state_path = f"{QUEUE}/{jid}.log", f"{QUEUE}/{jid}.state"
    try:
        spec = json.load(open(spec_path, encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return  # 書き込み途中（scp 中）なら次の周回で拾う
    os.rename(spec_path, spec_path + ".processing")
    real_err = sys.stderr
    saved = []
    with open(log_path, "a", encoding="utf-8", buffering=1) as logf:
        sys.stderr = logf  # tqdm（Denoising steps）をジョブのログへ
        try:
            t0 = time.time()
            print(f"start {jid}: {len(spec['jobs'])} job(s) size={spec.get('size')} steps={spec.get('steps')}", file=logf, flush=True)
            for j in spec["jobs"]:
                for c in j["control"]:
                    if not os.path.isfile(c):
                        raise FileNotFoundError(f"control image not found: {c}")
                p = edit_one(j, spec.get("out") or f"{ROOT}/output/edit", spec.get("size") or [1024, 1024],
                             int(spec.get("steps") or 25), float(spec.get("guidance") or 4.0))
                saved.append(p)
                print(f"saved: {p}", file=logf, flush=True)
            print(f"done in {int(time.time() - t0)}s", file=logf, flush=True)
            with open(state_path, "w") as fh:
                fh.write("done " + " ".join(saved) + "\n")
        except Exception as e:
            traceback.print_exc(file=logf)
            with open(state_path, "w") as fh:
                fh.write(f"failed {type(e).__name__}: {e}\n")
        finally:
            sys.stderr = real_err
    print(f"[edit_server] {jid}: {'done' if saved else 'failed'}", flush=True)


while True:
    # 1 秒以上前に書かれた、中身のあるファイルだけ拾う（scp 書き込み中のものを避ける）
    now = time.time()
    specs = sorted(f for f in glob.glob(f"{QUEUE}/*.json")
                   if os.path.getsize(f) > 0 and now - os.path.getmtime(f) > 1.0)
    if specs:
        try:
            process(specs[0])
        except Exception:  # サーバ自体は落とさない
            traceback.print_exc()
            time.sleep(2)
        continue
    time.sleep(2)
