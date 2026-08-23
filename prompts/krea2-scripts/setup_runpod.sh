#!/bin/bash
# RunPod（PyTorch 2.8 / CUDA 12.8 テンプレート）に musubi-tuner と Krea 2 / Qwen-Image-Edit 一式を入れる
# /workspace は Network volume（Pod を消しても残る）。2 回目以降は取得済みのモデルをそのまま使う
# 使い方: bash setup_runpod.sh   （HF トークンは ~/.cache/huggingface/token に置いてから）
set -euo pipefail
W=/workspace/krea2
mkdir -p $W/{models,output,scripts,refs,dataset}
cd $W
apt-get update -qq >/dev/null 2>&1 && apt-get install -y -qq tmux git >/dev/null 2>&1 || true
if [ ! -d musubi-tuner ]; then git clone -q https://github.com/kohya-ss/musubi-tuner.git; fi
cd musubi-tuner
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
  source .venv/bin/activate
  pip install -q -U pip
  pip install -q torch torchvision --index-url https://download.pytorch.org/whl/cu128
  pip install -q -e .
else
  source .venv/bin/activate
fi
python -c "import torch; print('CUDA', torch.cuda.is_available(), torch.cuda.get_device_name(0), round(torch.cuda.get_device_properties(0).total_memory/1024**3), 'GB')"
cd $W/models
dl() { # repo path  → 既にあれば飛ばす
  [ -f "$2" ] && { echo "exists: $2"; return; }
  huggingface-cli download "$1" "$2" --local-dir . 2>&1 | tail -1
}
dl Comfy-Org/Qwen-Image_ComfyUI split_files/vae/qwen_image_vae.safetensors
dl Comfy-Org/Qwen3-VL text_encoders/qwen3vl_4b_bf16.safetensors
dl krea/Krea-2-Turbo turbo.safetensors
dl Comfy-Org/Qwen-Image-Edit_ComfyUI split_files/diffusion_models/qwen_image_edit_2511_bf16.safetensors
dl Comfy-Org/Qwen-Image_ComfyUI split_files/text_encoders/qwen_2.5_vl_7b.safetensors
ln -sf split_files/vae/qwen_image_vae.safetensors qwen_image_vae.safetensors
ln -sf text_encoders/qwen3vl_4b_bf16.safetensors qwen3vl_4b_bf16.safetensors
# 学習もするなら RAW（26GB）: dl krea/Krea-2-Raw raw.safetensors
du -sh $W/models
echo "SETUP_DONE"
