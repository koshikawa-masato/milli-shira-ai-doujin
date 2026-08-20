#!/bin/bash
# 同じプロンプト・同じ seed で各チェックポイントを生成し、compare/<run> に並べる（手順書 §8）
# 使い方: compare.sh <run名> "<プロンプト>" [seed=0] [steps="300 600 900 1200 1500 1800"] ["メモ"]
set -e
RUN="${1:?run required}"; PROMPT="${2:?prompt required}"; SEED="${3:-0}"; STEPS="${4:-300 600 900 1200 1500 1800}"; NOTE="${5:-}"
for s in $STEPS; do
  L=$(printf "%s/krea2/output/%s-%06d.safetensors" "$HOME" "$RUN" "$s")
  [ -f "$L" ] || { echo "skip (not found): $L"; continue; }
  NOTE="$NOTE" ~/krea2/scripts/gen.sh "$PROMPT" "$SEED" "$L" ~/krea2/output/compare/$RUN
done
# ベース（LoRA なし）も 1 枚
NOTE="$NOTE" ~/krea2/scripts/gen.sh "$PROMPT" "$SEED" "" ~/krea2/output/compare/$RUN
