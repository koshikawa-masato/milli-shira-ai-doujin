# kuropanda デザイン仕様とプロンプト定型文

2026-08-20〜21 に Krea 2 Turbo（LoRA なし）で検証して決めたもの。
ギャラリー: https://pi5-home-1.tail8ec65a.ts.net:8452/ の `inverted` / `hanafuda` フォルダに実例あり。

## キャラ仕様（固定する要素）

- 黒髪ボブ、黒〜こげ茶の目の日本人少女
- **白黒反転パンダのパーカー**: 黒いフード、フード頭頂部に白い丸耳 2 つ、フード前面（額の上）に白い丸い「目の縁」2 つ、本体は黒、カンガルーポケットは白
- **フードの裏地は可変**: 感情（喜怒哀楽）や月（花札 12 か月）で色・柄が変わる。これがこの子の"表現"

## 生成のコツ（Krea 2 Turbo）

- **"panda" という語を使わない**。使うとベースモデルの「白い顔に黒耳」に引き戻される。配色を文章で直接描写する
- テキストエンコーダは Qwen3-VL なので、タグ羅列より**英語の文章**で書く
- 同じ seed で裏地や表情の記述だけ変えると、構図が揃った差分が取れる（比較に最適）
- ただし seed 固定だと**表情が弱くなる**。表情を出したいときは seed を変えるか、表情の記述を文頭に置く

## 基本プロンプト（これを土台に `{lining}` `{face}` を差し替える）

```
A Japanese girl with black bob hair and dark brown eyes, wearing a black animal-ear hoodie.
The hood is black with two round white ears on top, and the front of the hood has two white circular patches around the eye area.
{lining}
The hoodie body is black with a white kangaroo pocket. {face} Standing, looking at viewer, white background.
```

### 裏地（`{lining}`）

単色（検証済み: 赤が最も映える）

```
The inside lining of the hood is bright crimson red.
```

喜怒哀楽（色＋柄。4 つとも柄は安定して出る）

| 感情 | lining | face |
|---|---|---|
| 喜 | `The inside lining of the hood is bright golden yellow with a pattern of small white stars.` | `She has a big happy open-mouth smile, eyes sparkling with joy.` |
| 怒 | `The inside lining of the hood is bright red with a pattern of orange flames.` | `She looks angry: furrowed brows, puffed cheeks, pouting mouth.` |
| 哀 | `The inside lining of the hood is pale sky blue with a pattern of small white raindrops.` | `She looks sad: teary watery eyes, downturned mouth, eyebrows raised in the middle.` |
| 楽 | `The inside lining of the hood is soft sakura pink with a pattern of small green bamboo leaves.` | `She looks relaxed and cheerful, eyes closed in a gentle content smile, head slightly tilted.` |

花札 12 か月（`The inside lining of the hood is a traditional Japanese hanafuda card pattern: {motif}.`）

| 月 | 絵柄 | motif |
|---|---|---|
| 1 | 松に鶴 | `green pine branches with a red-crowned white crane and a red sun on a black background` |
| 2 | 梅に鶯 | `red plum blossoms on dark branches with a small green bush warbler bird` |
| 3 | 桜に幕 | `pink cherry blossoms with a striped red and purple curtain` |
| 4 | 藤にほととぎす | `hanging purple wisteria clusters with a small cuckoo bird and a crescent moon` |
| 5 | 菖蒲に八橋 | `purple iris flowers with a zigzag wooden bridge, green leaves` |
| 6 | 牡丹に蝶 | `large red peony flowers with a purple butterfly` |
| 7 | 萩に猪 | `red bush clover with a black wild boar` |
| 8 | 芒に月 | `silver pampas grass under a large full moon on a red sky, black hill` |
| 9 | 菊に盃 | `yellow chrysanthemum flowers with a red sake cup` |
| 10 | 紅葉に鹿 | `red and orange maple leaves with a brown deer` |
| 11 | 柳に雨 | `green willow branches in the rain with a small frog and purple lightning` |
| 12 | 桐に鳳凰 | `purple paulownia flowers and green leaves with a golden phoenix` |

花札の絵柄自体は伝統意匠で著作権はない（特定メーカーの描き起こしを写さないこと）。

## LoRA 学習時のキャプション方針

裏地は「バラす要素」なので、**毎回キャプションに裏地を書く**（`red flame hood lining` など）。
固定要素（黒フード・白耳・白い目の縁・白ポケット・黒髪ボブ）は `kuropanda` に含めて**書かない**。
→ 学習後は `kuropanda, yellow star hood lining, smiling` のように裏地を呼び分けられる。

## 検証履歴

- 2026-08-20 `inverted` seed 0: 反転配色が一発で成立（"panda" 回避が効いた）
- 2026-08-20 裏地 3 色比較（赤 / 竹緑 / 桜ピンク）→ 赤が最も視認性が高い
- 2026-08-20 喜怒哀楽 4 枚: 柄は 4 つとも成立、表情は seed 固定のため弱い
- 2026-08-21 花札 12 か月シリーズ `hanafuda` フォルダ
