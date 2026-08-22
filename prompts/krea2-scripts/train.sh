#!/bin/bash
# LoRA 学習（手順書 §6〜§7）を実行し、設定・素材・チェックポイントを履歴に記録する
# 使い方: train.sh <run名> [max_steps=1800] [save_every=300] [dim=32] [lr=1e-4] [blocks_to_swap=16] ["メモ"]
#   例: tmux new -s krea2 '~/krea2/scripts/train.sh kuropanda_v1 1800 300 32 1e-4 16 "初回。素材24枚"'
set -e
export PATH=$PATH:/usr/lib/wsl/lib
RUN="${1:?run name required}"; STEPS="${2:-1800}"; EVERY="${3:-300}"; DIM="${4:-32}"; LR="${5:-1e-4}"; SWAP="${6:-16}"; NOTE="${7:-}"
DS="${DATASET_DIR:-$HOME/krea2/dataset/images}"        # 環境変数で別データセット
TOML="${DATASET_TOML:-$HOME/krea2/dataset.toml}"
GFOLDER="${GALLERY_FOLDER:-dataset}"
cd ~/krea2/musubi-tuner && source .venv/bin/activate
N=$(ls "$DS"/*.png "$DS"/*.jpg 2>/dev/null | wc -l)
[ "$N" -gt 0 ] || { echo "dataset is empty: $DS"; exit 1; }
DATASET_JSON=$(python3 - "$DS" <<'PY'
import json,sys,pathlib
d=pathlib.Path(sys.argv[1]); out=[]
for f in sorted(d.iterdir()):
    if f.suffix.lower() in (".png",".jpg",".jpeg"):
        t=f.with_suffix(".txt"); out.append({"file":f.name,"caption":t.read_text().strip() if t.exists() else ""})
print(json.dumps(out,ensure_ascii=False))
PY
)
CMD="accelerate launch --num_cpu_threads_per_process 1 --mixed_precision bf16 \
  src/musubi_tuner/krea2_train_network.py \
  --dit ~/krea2/models/raw.safetensors --vae ~/krea2/models/qwen_image_vae.safetensors \
  --dataset_config $TOML --sdpa --mixed_precision bf16 \
  --timestep_sampling shift --weighting_scheme none --discrete_flow_shift 2.5 \
  --optimizer_type adamw8bit --learning_rate $LR --gradient_checkpointing \
  --max_data_loader_n_workers 2 --persistent_data_loader_workers \
  --network_module networks.lora_krea2 --network_dim $DIM --network_alpha $DIM \
  --fp8_base --fp8_scaled --blocks_to_swap $SWAP \
  --max_train_steps $STEPS --save_every_n_steps $EVERY --seed 42 \
  --output_dir ~/krea2/output --output_name $RUN"
START_JSON=$(python3 - "$RUN" "$STEPS" "$EVERY" "$DIM" "$LR" "$SWAP" "$NOTE" "$DATASET_JSON" "$CMD" "$GFOLDER" <<'PY'
import json,sys
run,steps,every,dim,lr,swap,note,ds,cmd=sys.argv[1:10]
print(json.dumps({"event":"train_start","run":run,"dataset_folder":sys.argv[10] if len(sys.argv)>10 else "dataset","dataset":json.loads(ds),
  "config":{"max_train_steps":int(steps),"save_every_n_steps":int(every),"network_dim":int(dim),"learning_rate":lr,
            "blocks_to_swap":int(swap),"base":"Krea-2 Raw","resolution":"512 (bucket)","seed":42},
  "note":note or None,"command":" ".join(cmd.split())},ensure_ascii=False))
PY
)
~/krea2/scripts/event.sh "$START_JSON" || true
T0=$(date +%s)
echo "== cache latents =="
python src/musubi_tuner/krea2_cache_latents.py --dataset_config $TOML --vae ~/krea2/models/qwen_image_vae.safetensors
echo "== cache text encoder =="
python src/musubi_tuner/krea2_cache_text_encoder_outputs.py --dataset_config $TOML --text_encoder ~/krea2/models/qwen3vl_4b_bf16.safetensors --batch_size 1
echo "== train =="
STATUS=done
eval "$CMD" || STATUS=failed
MIN=$(( ($(date +%s) - T0) / 60 ))
CKS=$(ls ~/krea2/output/${RUN}*.safetensors 2>/dev/null | xargs -n1 basename | python3 -c 'import json,sys; print(json.dumps([l.strip() for l in sys.stdin if l.strip()]))')
END_JSON=$(python3 -c 'import json,sys; print(json.dumps({"event":"train_end","run":sys.argv[1],"status":sys.argv[2],"duration_min":int(sys.argv[3]),"checkpoints":json.loads(sys.argv[4])}))' "$RUN" "$STATUS" "$MIN" "$CKS")
~/krea2/scripts/event.sh "$END_JSON" || true
echo "train $STATUS ($MIN min): $CKS"
[ "$STATUS" = done ]
