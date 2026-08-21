#!/bin/bash
# 同じプロンプト・同じ seed で各チェックポイントを生成し、compare/<run> に並べる（手順書 §8）
# 使い方: compare.sh <run名> "<プロンプト>" [seed=0] [steps="300 600 900 1200 1500 1800"] ["メモ"]
set -e
RUN="${1:?run required}"; PROMPT="${2:?prompt required}"; SEED="${3:-0}"; STEPS="${4:-}"; NOTE="${5:-}"
if [ -z "$STEPS" ]; then
  # 存在するチェックポイントの step を列挙（昇順）
  STEPS=$(ls "$HOME"/krea2/output/"$RUN"-step*.safetensors "$HOME"/krea2/output/"$RUN"-[0-9][0-9][0-9][0-9][0-9][0-9].safetensors 2>/dev/null \
    | sed -E 's/.*-(step)?0*([0-9]+)\.safetensors$/\2/' | sort -n | uniq | tr '\n' ' ')
  [ -n "$STEPS" ] || { echo "no checkpoints for $RUN"; exit 1; }
fi
echo "compare steps: $STEPS"
for s in $STEPS; do
  # musubi-tuner の保存名は <run>-step<8桁>.safetensors（旧: <run>-<6桁>）。どちらも拾う
  L=$(ls "$HOME/krea2/output/$RUN-step$(printf %08d "$s").safetensors" "$HOME/krea2/output/$RUN-$(printf %06d "$s").safetensors" 2>/dev/null | head -1)
  [ -n "$L" ] && [ -f "$L" ] || { echo "skip (not found): $RUN step $s"; continue; }
  NOTE="$NOTE" ~/krea2/scripts/gen.sh "$PROMPT" "$SEED" "$L" ~/krea2/output/compare/$RUN
done
# ベース（LoRA なし）も 1 枚
NOTE="$NOTE" ~/krea2/scripts/gen.sh "$PROMPT" "$SEED" "" ~/krea2/output/compare/$RUN
