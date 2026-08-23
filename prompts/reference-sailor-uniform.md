# 参考: セーラー服の描き方（三面図の判定基準に使う）

出典: アタムアカデミー「セーラー服のイラスト描き方」 https://atam-academy.com/blog/48323/ （2025-09-03）
天の声の指示で学習（2026-08-23）。ユカリの制服（鈴鹿高校夏服）の生成・編集結果をチェックするときの基準に使う。

## 構造の要点（そのまま判定基準になる）
- セーラーカラーは「体に密着した服の一部」ではなく**肩の上に載せた一枚の布**。背中側は平らな四角、前側は胸元へ向かう V。体の曲線に完全には沿わず、**肩や背中から少し浮く**。襟の下に細い影
- 胴体は厚い生地で、**胸の頂点から真下へまっすぐ落ちる**（ウエストを絞らない）。この直線がセーラー服らしいシルエット → ユカリの「箱型の裾」「細身だが横幅を出さない」と一致
- パーツ: セーラーカラー／セーラーテープ（縁のライン）／胸当て／スカーフ・リボン／後ろファスナー。**ユカリの制服は「テープ 2 本、胸当てなし、スカーフなし、前開きボタン」**なので、生成で胸当てやスカーフが出たら NG
- 色は彩度を抑え、**3 色程度**（白・紺・深緑）。色数が増えると顔より服に目が行く

## 角度別のチェック
| 向き | 見るところ |
|---|---|
| 正面 | 襟は「両肩先と胸元中心を結ぶ三角形」に収まる。肩幅に対して小さすぎると首が詰まり、大きすぎると肩から落ちそうに見える。首の後ろへ回り込む襟の厚みを描く |
| 横 | 襟の前側は胸のふくらみに沿って**斜めに下がる**、後ろ側は背中の平面に沿って**まっすぐ垂れる**。前の線は胸の頂点から真下、背中の線は肩甲骨の丸みでわずかに膨らむ。その差が体の厚み |
| 後ろ | 背中を覆う四角い襟が主役。**両肩を結ぶ線と襟の裾の線が平行な台形**。平行が崩れるとねじれて着崩れに見える。首の付け根→両肩先→襟裾中心の三角形に、背中の丸みぶんのわずかな傾斜 |

## 夏服の描き分け
- 薄手なので**細かく複雑なシワ**が寄る。裾や袖口を少し体から浮かせると夏らしい軽さ
- （冬服は厚手ウールで大きく少ないシワ、硬いシルエット。冬服を決めるときに使う）

## プリーツスカート
- 中心の前箱ヒダから左右へ細かいヒダ。山折り（明）と谷折り（暗）の縦ストライプで厚みを出す
- ユカリはグレーのプリーツ膝丈

## 生成・編集への翻訳（プロンプトに書くときの言い回し）
- 襟: `a white sailor collar that sits on her shoulders like a flat piece of cloth, square at the back, V-shaped at the front, slightly lifted from the body with a thin shadow beneath`
- 胴: `a boxy blouse that falls straight down from the bust without waist shaping`
- 後ろ: `the square back flap of the sailor collar hangs flat with its bottom edge parallel to the shoulder line`
- 横: `the front of the collar slopes down along the chest while the back flap hangs straight`
- 禁止: `no neckerchief, no scarf, no breast panel (胸当て), no ribbon`
- 夏服: `thin lightweight fabric with fine wrinkles, hem slightly floating from the body`
