#!/bin/bash
# 使い方: event.sh '<JSON>'   例: event.sh '{"event":"note","text":"..."}'
# ~/krea2/.gallery_env の GALLERY_URL / GALLERY_TOKEN を使う。ローカル履歴にも追記。
set -e
source ~/krea2/.gallery_env
JSON="${1:?json required}"
mkdir -p ~/krea2/output
python3 - "$JSON" >> ~/krea2/output/history.jsonl <<'PY'
import json,sys,time
d=json.loads(sys.argv[1]); d.setdefault("ts",time.strftime("%Y-%m-%dT%H:%M:%S")); print(json.dumps(d,ensure_ascii=False))
PY
curl -sS -m 30 -H "Authorization: Bearer $GALLERY_TOKEN" -H "Content-Type: application/json" \
  -d "$JSON" "$GALLERY_URL/api/event"
echo
