#!/bin/bash
# 使い方: gen.sh "プロンプト" [seed] [LoRAパス] [出力dir]
# Krea 2 Turbo で生成。LoRA 無しなら第3引数を省略。
set -e
export PATH=$PATH:/usr/lib/wsl/lib
PROMPT="${1:?prompt required}"
SEED="${2:-0}"
LORA="${3:-}"
OUT="${4:-$HOME/krea2/output/compare}"
mkdir -p "$OUT"
cd ~/krea2/musubi-tuner
source .venv/bin/activate
ARGS=()
if [ -n "$LORA" ]; then ARGS+=(--lora_weight "$LORA" --lora_multiplier 1.0); fi
python src/musubi_tuner/krea2_generate_image.py \
  "$PROMPT" \
  --dit ~/krea2/models/turbo.safetensors \
  --vae ~/krea2/models/split_files/vae/qwen_image_vae.safetensors \
  --text_encoder ~/krea2/models/text_encoders/qwen3vl_4b_bf16.safetensors \
  --steps 8 --guidance_scale 1 --mu 1.15 \
  --width 1024 --height 1024 \
  --attn_mode torch \
  --seed "$SEED" \
  --save_path "$OUT" \
  --fp8_scaled \
  "${ARGS[@]}"
