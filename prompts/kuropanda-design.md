# kuropanda デザイン仕様とプロンプト定型文

2026-08-20〜21 に Krea 2 Turbo（LoRA なし）で検証して決めたもの。
ギャラリー: https://pi5-home-1.tail8ec65a.ts.net:8452/ の `inverted` / `hanafuda` フォルダに実例あり。

## キャラ仕様（固定する要素）

基準画像（v2〜）: `circlecut/20260821-194041-801_0.png`（サークルカット採用。v1 LoRA step 1200 で生成、黒目は手描き。2026-08-22）
基準画像（v1）: `candidates/20260821-092837-966_0.png`（手を振る、教室。2026-08-21 に ★ 採用）

- 黒髪ボブ、黒〜こげ茶の目の日本人少女
- **白黒反転パンダのパーカー**: 黒いフード、フード頭頂部に白い丸耳 2 つ、フード前面（額の上）に白い丸い「目の縁」2 つ、本体は黒、カンガルーポケットは白
- **白い紐あり**
- **フードの縁は裏地の柄が幅広く見える**（黒一色だと見づらい）
- **白ポケットの縁に黒糸のステッチ**
- **ポケットの上端は白紐の先端より下**（胸まで上がっている絵は NG。2026-08-22 追加。v2 素材では 25 枚中 8 枚が該当 → v3 で除外）
- **服の皺は細い白ハイライト線**で描く
- 画風: アニメ塗り・クリーンな線画（背景指定で実写に振れるので、必ずプロンプト冒頭で画風を固定する）
- **フードの裏地は可変**: 感情（喜怒哀楽）や月（花札 12 か月）で色・柄が変わる。これがこの子の"表現"

## 生成のコツ（Krea 2 Turbo）

- **"panda" という語を使わない**。使うとベースモデルの「白い顔に黒耳」に引き戻される。配色を文章で直接描写する
- テキストエンコーダは Qwen3-VL なので、タグ羅列より**英語の文章**で書く
- 同じ seed で裏地や表情の記述だけ変えると、構図が揃った差分が取れる（比較に最適）
- ただし seed 固定だと**表情が弱くなる**。表情を出したいときは seed を変えるか、表情の記述を文頭に置く

## 正式プロンプト（2026-08-21 確定。**文面は固定、末尾の `{pose}` 一文だけ差し替える**）

基準画像 `candidates/20260821-092837-966_0.png` を出したプロンプトそのもの。「下手に小細工せずパターンを増やす」方針。

```
A Japanese girl with black bob hair and dark brown eyes, wearing a black animal-ear hoodie.
The hood is black with two round white ears on top, and the front of the hood has two white circular patches around the eye area.
The inside lining of the hood is a traditional Japanese hanafuda card pattern: red and orange maple leaves with a brown deer.
The hoodie body is black with a white kangaroo pocket. {pose}
```

`{pose}` の例: `Waving one hand, big happy open-mouth smile, upper body, classroom background.`（基準画像）

紐・縁の裏地・ステッチ・白ハイライトは**プロンプトで指定せず**、素材の選別（基準画像に近いものを選ぶ）と LoRA に委ねる。

## （不採用）基本プロンプト v2 案（2026-08-21。仕様を全部書き込んだ版。使わない）

```
Anime style illustration with clean lineart and flat colors.
A Japanese girl with black bob hair and dark brown eyes, wearing a black animal-ear hoodie with white drawstrings.
The hood is black with two round white ears on top, and the front of the hood has two white circular patches around the eye area.
{lining} The patterned lining is clearly visible along the wide rolled edge of the hood framing her face.
The hoodie body is black with a white kangaroo pocket that has visible black stitching along its edges.
Soft fabric wrinkles are drawn with thin white highlight lines on the black fabric.
{pose}
```

標準の裏地（正式）: `The inside lining of the hood is a traditional Japanese hanafuda card pattern: red and orange maple leaves with a brown deer.`（10月 紅葉に鹿）

旧 v1（2026-08-20。"panda" 回避・裏地可変の検証に使用）:

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
- 2026-08-21 花札 12 か月シリーズ `hanafuda` フォルダ → **10月 紅葉に鹿を正式裏地に採用**
- 2026-08-21 素材候補 20 枚 `candidates`: seed 1–8 で顔が安定することを確認。公園ベンチ指定は実写化した（画風アンカーが必要）。紐の有無が半々 → 紐ありに統一
- 2026-08-21 `candidates_v2`: 仕様を全部書いた v2 プロンプトで途中まで生成 → **不採用**（小細工せずパターンを増やす方針に変更）
- 2026-08-21 `patterns`: 正式プロンプト固定で `{pose}` 15 種 × 2 seed
- 2026-08-21 **kuropanda_v1 学習**: 素材 29 枚（基準 + patterns 28）、1800 step / dim 32 / lr 1e-4 / swap 16、185 分（6.1 s/it）、VRAM 12GB。loss 0.12 → 0.06。保存名は `kuropanda_v1-step00000300.safetensors` 形式
  - 同プロンプト比較: 300 で既に安定、1800 でも過学習の兆候なし。LoRA 版はフード縁の裏地が広く、耳の内側ピンク、**紐が消える**（キャプション未記載のため平均化）→ 生成時は `white drawstrings` を書くか、v2 でキャプションに入れる
  - 暫定採用候補 900 / 1200。トリガー語のみ・汎化テストは `trigger_test` フォルダ
- 2026-08-22 **v2 の素材生成開始**: 基準をサークルカットの子に更新。v1 LoRA step 1200 × **0.7**（顔は寄せつつ v1 の癖=耳ピンク・紐消えを薄める）で 15 ポーズ × 2 seed → `v2_src`。選別基準: 顔の幅/目の大きさが基準と同じ・白い紐あり・裏地が縁に見える・黒目あり（無ければ描き足す）・年齢が基準と同じ
- v2 の計画: トリガー語 `krpn`、キャプションは `krpn, 1girl, <ポーズ文>` のみ、2400 step / 400 ごと保存 / 解像度 768
- 2026-08-22 **v2 素材確定・学習投入**: `v2_src` 30 枚のうち耳の内側がピンクの 6 枚（01,02,07,08,25,26）を除外、24 枚に黒目を自動描画（白い目の縁を検出して 20% の黒丸）、残るピンクを耳領域限定で白化。判定を緩めすぎて肌まで白くした 6 枚は元からやり直し（教訓: 肌色と耳のピンクは近いので、耳の白領域の近傍に限定し閾値は厳しめに）
  - 登録: `dataset_v2/images/001–025`（001 = 基準）、キャプション `krpn, 1girl, <ポーズ文>`、`dataset_v2.toml` 解像度 768
  - 学習 `kuropanda_v2`: 2400 step / 400 ごと / dim 32 / lr 1e-4 / swap 24。学習後の比較は短文 `krpn, waving one hand, ...` のみ
- 2026-08-22 **NG ルール追加**「ポケットの上端は紐の先端より下」。v2 素材の 05,06,09,10,23,24,27,28 が該当（本を持つ・横顔・腕組み・白背景アップ）。腕を胸の前で組む／物を持つ構図と、バストアップの切り抜きでポケットが上がりやすい
- 2026-08-22 **kuropanda_v2 成功**: 素材 25 枚、トリガー `krpn`、キャプション `krpn, 1girl, <ポーズ文>`、768 / 2400 step / swap 24、6 時間 33 分（9.8 s/it）。**短文 `krpn, waving one hand, ...` だけで衣装一式（黒フード・白耳・黒目付きの目の縁・紅葉に鹿の裏地・白い紐・白ポケット・黒髪ボブ）が出る**。base は制服の少女（`krpn` に元の意味なし）、400 は熊、800 以降は安定。1600 はポケットが胸まで上がる（素材の NG 3 割の影響）。暫定採用 1200 / 2000
  - 教訓: **トリガー語に既知の単語を含めない**ことが決定的だった。v1 の `kuropanda` は `panda` に負けていた
  - 時短: 800 で十分出ているので、次回は 512 / 1000 step / swap 8 で 1 時間強を目標
- 2026-08-22 **v2 採用 step = 1200**（`kuropanda_v2-step00001200.safetensors`）。汎化テスト: 自転車・夕日 / 全身後ろ姿 / 全身正面 は 1200・2000 とも衣装を保持。裏地の呼び分け（`the hood lining is bright red with orange flame pattern`）は 1200 が裏地だけ赤くなり正解、2000 はパーカー全体が赤に滲む（学習が進むほど指示に対して硬くなる）。既知の癖: 後ろ姿で背中にポケットが出る（v3 で後ろ姿の素材を入れて矯正）
