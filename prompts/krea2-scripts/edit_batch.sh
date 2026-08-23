#!/bin/bash
# Qwen-Image-Edit-2511 で複数の編集を 1 プロセスで連続処理する（モデル読込 1 回で済ませる）
# 使い方: edit_batch.sh <jobs.jsonl> [出力dir]
#   jobs.jsonl の 1 行 = 1 ジョブ: {"prompt": "...", "control": ["元画像", "参照..."], "seed": 0, "note": "理由", "negative": "任意"}
#   control はギャラリー相対パス（~/krea2/output/ 基準）か絶対パス。先頭が派生元になる
#   環境変数は edit.sh と同じ: STEPS GUIDANCE BLOCKS_TO_SWAP SIZE NEGATIVE FP8 TE_CPU
# 出力は処理順に sidecar .json と history.jsonl を書き、.gallery_env があればアップロードする
set -e
export PATH=$PATH:/usr/lib/wsl/lib
JOBS="${1:?jobs.jsonl required}"
OUT="${2:-$HOME/krea2/output/edit}"
M=~/krea2/models
DIT=$M/split_files/diffusion_models/qwen_image_edit_2511_bf16.safetensors
TE=$M/split_files/text_encoders/qwen_2.5_vl_7b.safetensors
VAE=$M/qwen_image_vae.safetensors
mkdir -p "$OUT"
NEG_DEFAULT="${NEGATIVE:-lowres, blurry, bad anatomy, extra fingers, text, watermark}"
PROMPTS="$OUT/.batch_prompts_$$.txt"
# jobs.jsonl → musubi の from_file 形式（prompt --ci a --ci b --d seed --n negative）
python3 - "$JOBS" "$PROMPTS" "$NEG_DEFAULT" <<'PY'
import json,sys,os
jobs,dst,neg=sys.argv[1:]
home=os.path.expanduser("~")
def resolve(p): return p if p.startswith("/") else f"{home}/krea2/output/{p}"
lines=[]
for l in open(jobs,encoding="utf-8"):
    if not l.strip(): continue
    j=json.loads(l)
    ctrl=[resolve(c) for c in j["control"]]
    for c in ctrl:
        if not os.path.isfile(c): sys.exit(f"control image not found: {c}")
    s=j["prompt"].replace("\n"," ")
    for c in ctrl: s+=f" --ci {c}"
    s+=f" --d {int(j.get('seed',0))} --n {j.get('negative') or neg}"
    lines.append(s)
open(dst,"w",encoding="utf-8").write("\n".join(lines)+"\n")
print(f"{len(lines)} jobs")
PY
cd ~/krea2/musubi-tuner && source .venv/bin/activate
BEFORE=$(mktemp); ls "$OUT"/*.png 2>/dev/null | sort > "$BEFORE" || true
T0=$(date +%s)
# shellcheck disable=SC2086
python src/musubi_tuner/qwen_image_generate_image.py \
  --dit "$DIT" --vae "$VAE" --text_encoder "$TE" \
  --model_version edit-2511 \
  --from_file "$PROMPTS" \
  --resize_control_to_official_size \
  --image_size ${SIZE:-1024 1024} --infer_steps "${STEPS:-25}" --guidance_scale "${GUIDANCE:-4.0}" \
  --attn_mode torch $( [ "${FP8:-1}" = "1" ] && echo --fp8_scaled ) $( [ "${TE_CPU:-1}" = "1" ] && echo --text_encoder_cpu ) \
  $( [ "${BLOCKS_TO_SWAP:-20}" != "0" ] && echo --blocks_to_swap "${BLOCKS_TO_SWAP:-20}" ) \
  --save_path "$OUT"
echo "batch elapsed $(( $(date +%s) - T0 ))s"
# 新しい出力を古い順に並べ、ジョブの順に対応づける
NEW=$(ls -tr "$OUT"/*.png 2>/dev/null | sort | comm -13 "$BEFORE" - | xargs -I{} stat -c '%Y {}' {} | sort -n | cut -d' ' -f2-)
rm -f "$BEFORE"
FOLDER=${OUT#$HOME/krea2/output/}; [ "$FOLDER" = "$OUT" ] && FOLDER=$(basename "$OUT")
python3 - "$JOBS" "$FOLDER" "${STEPS:-25}" "${GUIDANCE:-4.0}" $NEW >> ~/krea2/output/history.jsonl <<'PY'
import json,sys,time,os
jobs,folder,steps,g=sys.argv[1:5]; outs=sys.argv[5:]
home=os.path.expanduser("~")
J=[json.loads(l) for l in open(jobs,encoding="utf-8") if l.strip()]
if len(J)!=len(outs): print(f"WARN: {len(J)} jobs but {len(outs)} outputs", file=sys.stderr)
for j,path in zip(J,outs):
    src=j["control"][0]; src=src[len(home)+len("/krea2/output/"):] if src.startswith(home+"/krea2/output/") else src
    meta={"stage":"gen","tool":"qwen-image-edit-2511","prompt":j["prompt"],"seed":int(j.get("seed",0)),"parent":src,"control":src,
          "refs":j["control"][1:] or None,"steps":int(steps),"guidance_scale":float(g),"note":j.get("note") or None,"batch":True}
    json.dump(meta,open(path+".json","w",encoding="utf-8"),ensure_ascii=False)
    print(json.dumps({"ts":time.strftime("%Y-%m-%dT%H:%M:%S"),"event":"gen","path":path,"folder":folder,"meta":meta},ensure_ascii=False))
    print(f"saved: {path}", file=sys.stderr)
PY
if [ -f ~/krea2/.gallery_env ]; then
  for f in $NEW; do ~/krea2/scripts/upload.sh "$f" "$FOLDER" "$(cat "$f.json")" || echo "upload failed ($f)"; done
fi
rm -f "$PROMPTS"
