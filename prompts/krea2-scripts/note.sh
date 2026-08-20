#!/bin/bash
# 使い方: note.sh "メモ本文" [対象画像の相対パス]
# 例: note.sh "フードの耳が小さい。プロンプトに big panda ears を足す" test/20260820-175904-930_0.png
set -e
TEXT="${1:?text required}"; REF="${2:-}"
JSON=$(python3 -c 'import json,sys; print(json.dumps({"event":"note","text":sys.argv[1],"ref":sys.argv[2] or None},ensure_ascii=False))' "$TEXT" "$REF")
~/krea2/scripts/event.sh "$JSON"
