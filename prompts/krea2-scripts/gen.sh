#!/bin/bash
# 使い方: gen.sh "プロンプト" [seed] [LoRAパス] [出力dir]
#   環境変数 NOTE="..." を付けると「なぜこのプロンプトにしたか」を一緒に記録できる
#   環境変数 PARENT="test/2026...png" で派生元画像（ギャラリー上の相対パス）を明示できる。無指定ならプロンプト類似で推定
#   例: NOTE="耳を大きく" gen.sh "kuropanda, big panda ears, ..." 0 "" ~/krea2/output/test
# Krea 2 Turbo で生成し、Pi5 ギャラリーへ自動アップロード。LoRA 無しなら第3引数を "" にする。
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
# LoRA 適用時は VRAM が溢れて極端に遅くなる（16GB で 1 枚 14 分）ので、ブロックの一部を CPU に退避する
# 環境変数 BLOCKS_TO_SWAP で上書き可（0 で無効）
if [ -n "$LORA" ]; then
  ARGS+=(--lora_weight "$LORA" --lora_multiplier "${LORA_MULTIPLIER:-1.0}")
  SWAP="${BLOCKS_TO_SWAP:-12}"
else
  SWAP="${BLOCKS_TO_SWAP:-0}"
fi
if [ "$SWAP" != "0" ]; then ARGS+=(--blocks_to_swap "$SWAP"); fi
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
  META=$(python3 - "$PROMPT" "$SEED" "$LORA" "$DIT" $STEPS $GUIDANCE $MU "${NOTE:-}" "${PARENT:-}" "${LORA_MULTIPLIER:-1.0}" <<'PY'
import json,sys,re,os
p,seed,lora,dit,steps,g,mu,note,parent,mult=sys.argv[1:]
run=step=None
if lora:
    m=re.match(r"^(.+?)-(?:step)?(\d{6,8})\.safetensors$", os.path.basename(lora))
    if m: run,step=m.group(1),int(m.group(2))
    else: run=os.path.basename(lora).replace(".safetensors","")
print(json.dumps({"stage":"gen","prompt":p,"seed":int(seed),"lora":lora or None,"lora_multiplier":float(mult) if lora else None,
  "run":run,"step":step,"dit":os.path.basename(dit),"steps":int(steps),"guidance_scale":float(g),"mu":float(mu),
  "width":1024,"height":1024,"note":note or None,"parent":parent or None},ensure_ascii=False))
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
