#!/bin/bash
# 使い方: gen.sh "プロンプト" [seed] [LoRAパス] [出力dir]
# Krea 2 Turbo で生成し、Pi5 のギャラリーへ自動アップロード。LoRA 無しなら第3引数を "" にする。
set -e
export PATH=$PATH:/usr/lib/wsl/lib
PROMPT="${1:?prompt required}"
SEED="${2:-0}"
LORA="${3:-}"
OUT="${4:-$HOME/krea2/output/compare}"
STEPS=8; GUIDANCE=1; MU=1.15; W=1024; H=1024
DIT=~/krea2/models/turbo.safetensors
mkdir -p "$OUT"
cd ~/krea2/musubi-tuner
source .venv/bin/activate
ARGS=()
if [ -n "$LORA" ]; then ARGS+=(--lora_weight "$LORA" --lora_multiplier 1.0); fi
BEFORE=$(ls -t "$OUT"/*.png 2>/dev/null | head -1)
python src/musubi_tuner/krea2_generate_image.py \
  "$PROMPT" \
  --dit "$DIT" \
  --vae ~/krea2/models/qwen_image_vae.safetensors \
  --text_encoder ~/krea2/models/qwen3vl_4b_bf16.safetensors \
  --steps $STEPS --guidance_scale $GUIDANCE --mu $MU \
  --width $W --height $H \
  --attn_mode torch \
  --seed "$SEED" \
  --save_path "$OUT" \
  --fp8_scaled \
  "${ARGS[@]}"
NEW=$(ls -t "$OUT"/*.png 2>/dev/null | head -1)
if [ -n "$NEW" ] && [ "$NEW" != "$BEFORE" ]; then
  META=$(python - "$PROMPT" "$SEED" "$LORA" "$DIT" $STEPS $GUIDANCE $MU <<'PY'
import json,sys
p,seed,lora,dit,steps,g,mu=sys.argv[1:]
print(json.dumps({"prompt":p,"seed":int(seed),"lora":lora or None,"lora_multiplier":1.0 if lora else None,
  "dit":dit,"steps":int(steps),"guidance_scale":float(g),"mu":float(mu)},ensure_ascii=False))
PY
)
  echo "$META" > "$NEW.json"
  FOLDER=$(basename "$OUT")
  if [ -f ~/krea2/.gallery_env ]; then
    ~/krea2/scripts/upload.sh "$NEW" "$FOLDER" "$META" || echo "upload failed (image kept at $NEW)"
  fi
  echo "saved: $NEW"
fi
