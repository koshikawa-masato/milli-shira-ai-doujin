"""RunPod Serverless ワーカー: Qwen-Image-Edit-2511（musubi-tuner）で画像編集
起動時にモデル一式を GPU に常駐させ、以後はジョブごとにデノイズだけを行う。

入力 job["input"]:
  prompt      編集指示（必須）
  control     参照画像の base64 PNG/JPEG の配列（必須、先頭が元画像）
  negative    ネガティブ（省略時は既定）
  seed        既定 0
  width/height  出力サイズ（既定 1024x1024、16 の倍数）
  steps       既定 25
  guidance    既定 4.0
出力: {"image": base64 PNG, "seed", "width", "height", "elapsed_sec"}
モデルは Network volume（KREA2_ROOT=/runpod-volume/krea2）の models/ から読む。
"""
import base64
import io
import os
import sys
import time
import traceback

import runpod
import torch
from PIL import Image

ROOT = os.environ.get("KREA2_ROOT", "/runpod-volume/krea2")
M = f"{ROOT}/models"
NEG_DEFAULT = "lowres, blurry, bad anatomy, extra fingers, text, watermark"
TMP = "/tmp/krea2-edit"
os.makedirs(TMP, exist_ok=True)

from musubi_tuner import qwen_image_generate_image as q  # noqa: E402

T_LOAD = time.time()
sys.argv = ["handler",
            "--dit", f"{M}/split_files/diffusion_models/qwen_image_edit_2511_bf16.safetensors",
            "--vae", f"{M}/qwen_image_vae.safetensors",
            "--text_encoder", f"{M}/split_files/text_encoders/qwen_2.5_vl_7b.safetensors",
            "--model_version", "edit-2511", "--attn_mode", "torch", "--resize_control_to_official_size",
            "--image_size", "1024", "1024", "--infer_steps", "25", "--guidance_scale", "4.0",
            "--prompt", "warmup", "--negative_prompt", NEG_DEFAULT, "--save_path", TMP]
ARGS = q.parse_args()
if ARGS.device is None:  # CLI では main() が補う値
    ARGS.device = "cuda" if torch.cuda.is_available() else "cpu"
GEN = q.get_generation_settings(ARGS)
DEVICE = GEN.device
# テキストエンコーダ・VL processor（CPU に読み込まれるので GPU へ）
TE = q.load_shared_models(ARGS)
TE["text_encoder"].to(DEVICE)
TE["conds_cache"] = {}
VAE = q.load_vae(ARGS, DEVICE)
VAE.eval()
DIT = q.load_dit_model(ARGS, DEVICE, GEN.dit_weight_dtype)
DIT_SHARED = {"model": DIT}
print(f"[handler] models loaded in {time.time() - T_LOAD:.0f}s; "
      f"VRAM {torch.cuda.memory_allocated() / 2**30:.1f} GiB", flush=True)


def _decode_images(items: list[str]) -> list[str]:
    paths = []
    for i, b64 in enumerate(items):
        raw = base64.b64decode(b64.split(",", 1)[-1])
        im = Image.open(io.BytesIO(raw)).convert("RGB")
        p = f"{TMP}/ctrl_{os.getpid()}_{time.time_ns()}_{i}.png"
        im.save(p)
        paths.append(p)
    return paths


def handler(job: dict) -> dict:
    inp = job.get("input") or {}
    t0 = time.time()
    prompt = (inp.get("prompt") or "").strip()
    ctrl_b64 = inp.get("control") or []
    if not prompt or not ctrl_b64:
        return {"error": "prompt and control (base64 image list) are required"}
    paths = _decode_images(ctrl_b64)
    try:
        w = int(inp.get("width") or 1024)
        h = int(inp.get("height") or 1024)
        if w % 16 or h % 16 or not (256 <= w <= 2048 and 256 <= h <= 2048):
            return {"error": "width/height must be multiples of 16 in 256..2048"}
        args = q.apply_overrides(ARGS, {
            "prompt": prompt,
            "negative_prompt": inp.get("negative") or NEG_DEFAULT,
            "seed": int(inp.get("seed") or 0),
            "infer_steps": int(inp.get("steps") or 25),
            "guidance_scale": float(inp.get("guidance") or 4.0),
            "control_image_path": paths,
            "image_size_width": w, "image_size_height": h,
        })
        with torch.no_grad():
            control_latents, control_nps = q.prepare_image_inputs(args, DEVICE, VAE)
            TE["conds_cache"].clear()
            context, context_null = q.prepare_text_inputs(args, control_nps, DEVICE, TE)
            _, latent = q.generate(args, GEN, DIT_SHARED,
                                   precomputed_text_data={"context": context, "context_null": context_null,
                                                          "control": (control_latents, control_nps)})
            pixels = q.decode_latent(VAE, latent, DEVICE)  # (1,3,H,W) float32 in [0,1]（save_images_grid と同じ扱い）
        arr = (pixels[0].permute(1, 2, 0).clamp(0, 1) * 255).round().to(torch.uint8).numpy()
        buf = io.BytesIO()
        Image.fromarray(arr).save(buf, format="PNG")
        if os.environ.get("HANDLER_DEBUG_DIR"):  # ローカルテスト用: 画像をファイルにも残す
            os.makedirs(os.environ["HANDLER_DEBUG_DIR"], exist_ok=True)
            with open(os.path.join(os.environ["HANDLER_DEBUG_DIR"], f"{job.get('id', 'job')}.png"), "wb") as fh:
                fh.write(buf.getvalue())
        return {"image": base64.b64encode(buf.getvalue()).decode(), "seed": args.seed,
                "width": int(arr.shape[1]), "height": int(arr.shape[0]), "elapsed_sec": round(time.time() - t0, 1)}
    except Exception as e:  # SDK が FAILED にするが、原因を output にも残す
        traceback.print_exc()
        return {"error": f"{type(e).__name__}: {e}"}
    finally:
        for p in paths:
            try:
                os.remove(p)
            except OSError:
                pass


runpod.serverless.start({"handler": handler})
