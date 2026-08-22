#!/bin/bash
# 学習素材（タネ画像）を dataset に追加し、作り方ごと記録する
# 使い方: dataset_add.sh <画像> "<キャプション>" [出所] ["作り方プロンプト"] ["メモ"]
#   出所の例: nano-banana / claude / krea2-base / hand / photo
#   環境変数 PARENT="test/xxx.png" で「この生成画像を素材化した」関係を記録できる
#   例: dataset_add.sh ~/in/a.png "kuropanda, 1girl, black panda hoodie, front view" nano-banana \
#         "A girl in a black panda hoodie, anime style, front view, white background" "正面の基準画像"
set -e
SRC="${1:?image required}"; CAPTION="${2:?caption required}"; SOURCE="${3:-unknown}"; HOW="${4:-}"; NOTE="${5:-}"
DS="${DATASET_DIR:-$HOME/krea2/dataset/images}"   # 環境変数 DATASET_DIR で別データセットに登録できる
GFOLDER="${GALLERY_FOLDER:-dataset}"               # ギャラリー上のフォルダ名
mkdir -p "$DS"
EXT="${SRC##*.}"; EXT="${EXT,,}"; [ "$EXT" = "jpeg" ] && EXT=jpg
N=$(ls "$DS"/*.png "$DS"/*.jpg 2>/dev/null | wc -l)
NAME=$(printf "%03d" $((N+1)))
# 名前が被ったら進める
while [ -e "$DS/$NAME.png" ] || [ -e "$DS/$NAME.jpg" ]; do N=$((N+1)); NAME=$(printf "%03d" $((N+1))); done
DEST="$DS/$NAME.$EXT"
cp "$SRC" "$DEST"
printf '%s\n' "$CAPTION" > "$DS/$NAME.txt"
META=$(python3 - "$CAPTION" "$SOURCE" "$HOW" "$NOTE" "$(basename "$SRC")" "${PARENT:-}" <<'PY'
import json,sys
c,s,h,n,o,parent=sys.argv[1:]
print(json.dumps({"stage":"dataset","caption":c,"source":s,"prompt":h or None,"note":n or None,"original":o,"parent":parent or None},ensure_ascii=False))
PY
)
echo "$META" > "$DEST.json"
echo "added: $DEST"
if [ -f ~/krea2/.gallery_env ]; then
  # ギャラリー上は dataset/<NAME>.<ext> で保存されるようにファイル名を揃える
  ~/krea2/scripts/upload.sh "$DEST" "$GFOLDER" "$META" || echo "upload failed (kept at $DEST)"
fi
