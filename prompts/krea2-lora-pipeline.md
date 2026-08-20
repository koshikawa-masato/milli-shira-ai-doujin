# ろてじん式 Krea 2 LoRA パイプライン

参照: https://x.com/rotejin/status/2089951396246528126
日付: 2026-08-20

## 対象の流れ

1. AIで画像素材を作る
2. キャプション付けと整理
3. Krea 2 用LoRAを学習
4. 1800 stepsまで作って比較し、1200 stepsを採用
5. LoRAを適用して生成
6. Real-ESRGANで拡大

## 守るルール

- 学習は Krea 2 RAW
- 推論は Krea 2 Turbo
- キャラLoRAなら 20–30枚
- 歩数の目安は 1000–1300
- 1800は比較用。過学習しやすい
