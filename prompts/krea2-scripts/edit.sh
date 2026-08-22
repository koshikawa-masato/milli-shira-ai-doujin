#!/bin/bash
# Qwen-Image-Edit-2511 で画像を編集する（顔の画素を保ったまま服・背景・表情を変える用）
# 使い方: edit.sh "<編集指示>" <元画像(ギャラリー相対パス or 絶対パス)> [seed] [出力dir] [追加の参照画像...]
#   例: edit.sh "Change her black hoodie into a white sailor school uniform. Keep her face, eyes and hair exactly the same." \
#         compare/kuropanda_v2/20260822-162704-170_0.png 0 ~/krea2/output/edit
#   環境変数: NOTE="理由"  STEPS=25  GUIDANCE=4.0  BLOCKS_TO_SWAP=20  SIZE="1024 1024"
# 出力は Pi5 ギャラリーへ自動アップロード（派生元 = 元画像）
set -e
export PATH=$PATH:/usr/lib/wsl/lib
PROMPT="${1:?edit prompt required}"
SRC="${2:?control image required}"
SEED="${3:-0}"
OUT="${4:-$HOME/krea2/output/edit}"
shift 4 2>/dev/null || shift $#
EXTRA=("$@")
resolve() { case "$1" in /*) echo "$1";; *) echo "$HOME/krea2/output/$1";; esac; }
CTRL=$(resolve "$SRC")
[ -f "$CTRL" ] || { echo "control image not found: $CTRL"; exit 1; }
CTRLS=("$CTRL"); for e in "${EXTRA[@]}"; do CTRLS+=("$(resolve "$e")"); done
M=~/krea2/models
DIT=$M/split_files/diffusion_models/qwen_image_edit_2511_bf16.safetensors
TE=$M/split_files/text_encoders/qwen_2.5_vl_7b.safetensors
VAE=$M/qwen_image_vae.safetensors
mkdir -p "$OUT"
cd ~/krea2/musubi-tuner && source .venv/bin/activate
BEFORE=$(ls -t "$OUT"/*.png 2>/dev/null | head -1)
# shellcheck disable=SC2086
python src/musubi_tuner/qwen_image_generate_image.py \
  --dit "$DIT" --vae "$VAE" --text_encoder "$TE" \
  --model_version edit-2511 \
  --control_image_path "${CTRLS[@]}" \
  --prompt "$PROMPT" \
  --resize_control_to_official_size \
  --image_size ${SIZE:-1024 1024} --infer_steps "${STEPS:-25}" --guidance_scale "${GUIDANCE:-4.0}" \
  --attn_mode sdpa --fp8_scaled --text_encoder_cpu \
  --blocks_to_swap "${BLOCKS_TO_SWAP:-20}" \
  --seed "$SEED" --save_path "$OUT"
NEW=$(ls -t "$OUT"/*.png 2>/dev/null | head -1)
if [ -n "$NEW" ] && [ "$NEW" != "$BEFORE" ]; then
  REL_SRC="$SRC"; case "$SRC" in /*) REL_SRC="${SRC#$HOME/krea2/output/}";; esac
  META=$(python3 - "$PROMPT" "$SEED" "$REL_SRC" "${NOTE:-}" "${STEPS:-25}" "${GUIDANCE:-4.0}" <<'PY'
import json,sys
p,seed,src,note,steps,g=sys.argv[1:]
print(json.dumps({"stage":"gen","tool":"qwen-image-edit-2511","prompt":p,"seed":int(seed),"parent":src,"control":src,
  "steps":int(steps),"guidance_scale":float(g),"note":note or None},ensure_ascii=False))
PY
)
  echo "$META" > "$NEW.json"
  FOLDER=${OUT#$HOME/krea2/output/}; [ "$FOLDER" = "$OUT" ] && FOLDER=$(basename "$OUT")
  python3 - "$NEW" "$FOLDER" "$META" >> ~/krea2/output/history.jsonl <<'PY'
import json,sys,time
path,folder,meta=sys.argv[1:]
print(json.dumps({"ts":time.strftime("%Y-%m-%dT%H:%M:%S"),"event":"gen","path":path,"folder":folder,"meta":json.loads(meta)},ensure_ascii=False))
PY
  if [ -f ~/krea2/.gallery_env ]; then
    ~/krea2/scripts/upload.sh "$NEW" "$FOLDER" "$META" || echo "upload failed (image kept at $NEW)"
  fi
  echo "saved: $NEW"
fi
