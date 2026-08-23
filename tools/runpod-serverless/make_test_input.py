# 手元の画像から handler のテスト入力 JSON を作る
# 使い方: python3 make_test_input.py out.json "プロンプト" 元画像.png [参照.png ...] [--seed N --w W --h H]
import base64, json, sys
a = sys.argv[1:]; out, prompt = a[0], a[1]
opts = {"seed": 0, "width": 1024, "height": 1024}
imgs = []
i = 2
while i < len(a):
    if a[i] == "--seed": opts["seed"] = int(a[i + 1]); i += 2
    elif a[i] == "--w": opts["width"] = int(a[i + 1]); i += 2
    elif a[i] == "--h": opts["height"] = int(a[i + 1]); i += 2
    else: imgs.append(base64.b64encode(open(a[i], "rb").read()).decode()); i += 1
json.dump({"input": {"prompt": prompt, "control": imgs, **opts}}, open(out, "w"))
print(out, len(imgs), "images")
