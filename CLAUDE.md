# photo-genka

X-E5 の写真1枚あたりの値段が見れるだけの WEB アプリ。
レンズキット支払総額 ÷ カメラ内シャッターカウンタ（ImageCount）= 「いま、1枚あたりいくらか」を表示する。

- 仕様書: Cosense の `photo-genka` ページ（kouki プロジェクト）が一次ソース。仕様の疑問はまずそこを読む
- 公開URL（予定）: https://x-e5.ojimpo.com （CF Tunnel 経由、認証なし公開 = health.ojimpo.com と同等）
- 汎用アプリではなく「この一台（X-E5）のためのページ」。将来別ボディを買ったら同じエンジンを別サブドメインでデプロイする

## 確定パラメータ（.env で管理、ハードコード禁止）

| 項目 | 値 | 備考 |
|---|---|---|
| 支払総額 | ¥248,310 | SMBCショッピングクレジット 48回無金利分割（カメラのキタムラ）。分子は総額固定（支払進捗は単価計算に影響させない） |
| 購入日 | 2026-07-06 | キラキラ減衰・グラフ起点・分割払い進捗の起点 |
| フィルム1本 | ¥2,500 | 24枚撮り前提。変更されうるので .env |
| 現像代 | ¥1,830 | 同上 |

## アーキテクチャ

- backend: FastAPI (Python 3.12) + SQLite（日次スナップショット）+ exiftool
- frontend: 素の HTML/CSS/JS（`docs/mockups/photo-genka-mock.html` のデザインが正）。FastAPI が静的配信
- Docker Compose: プロジェクト名 `photo-genka`、サービス名 `genka`、ホストポート **8403**（health=8401, strava=8402 の続き）
- Immich 連携: ホスト公開ポート経由（`host.docker.internal:2283`、extra_hosts で解決）。API キーは .env の `IMMICH_API_KEY`

## ドメイン知識（重要な実装ルール）

- **ImageCount** = Fujifilm Maker Notes タグ 0x1438。カメラ内カウンタで、撮って出し JPEG/HEIF/RAF に毎回埋め込まれる
- **32K ロールオーバー補正**: ImageCount は 16bit。前回スナップショットより小さくなったら +32,768（それでも小さければ +65,536）で単調増加に補正する。初期から実装済みであること
- 分母は Immich のアセット数**ではない**。Immich の最新 X-E5 アセットのオリジナルを1枚取得して exiftool で ImageCount を読む。アセット数集計は乖離チェック用の副次表示のみ
- ドロップされた写真は即時破棄・保存しない。HEIF(.HIF)/RAF 両対応、サイズ上限あり
- モバイル対策（viewport-fit=cover、overscroll-behavior: none 等）は health-ojimpo リポジトリの設定を踏襲する

## 演出まわり

- キラキラ減衰 = 時間ベース（経過日数 ÷ 365 で opacity 1→0）
- アタリ（塗装剥げ）= 枚数マイルストーンで段階的出現。レイヤー方式（ベース画像は不変、差分レイヤーを重ねる）
- 状態違いをまるごと画像生成し直すのは**禁止**（カメラが別物に化ける）
- アタリのマイルストーン枚数は iPhone の年間撮影実績から較正する（Immich API キー入手後のタスク）

## 開発ルール

- コミットは細かく切る（feat:/fix: + 日本語サマリ、health-ojimpo のスタイルに合わせる）
- .env は .gitignore に含める。.env.example を必ず同期させる
- ユーザーへの応答は日本語ですます調
