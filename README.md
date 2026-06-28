# 日本版 Fear &amp; Greed Index

日本株式市場の投資家心理を、複数の独立した市場指標から **0〜100 の単一スコア**に
合成する自作インデックスです。CNN の Fear &amp; Greed Index と同型の設計思想（複数指標を
正規化して合成）を、**日本市場に最適化した指標構成・一次データソース**で実装します。

> ⚠ 本指標は **情報提供目的の自作指標であり、投資助言ではありません。**

---

## スコアの意味（判定バンド）

| スコア | 状態 |
| --- | --- |
| 0–25 | 極度の恐怖 (Extreme Fear) |
| 25–45 | 恐怖 (Fear) |
| 45–55 | 中立 (Neutral) |
| 55–75 | 貪欲 (Greed) |
| 75–100 | 極度の貪欲 (Extreme Greed) |

## 指標構成（8指標 / 6次元）

| # | 指標 | 次元 | 高い値の意味 | 重み | 主データソース |
| --- | --- | --- | --- | --- | --- |
| 1 | 日経225 vs 125日線乖離率 | モメンタム | Greed | 1/6 | 指数価格（J-Quants / stooq） |
| 2 | 騰落レシオ（東証プライム・25日） | ブレッドス | Greed | 1/12 | 東証 値上がり/値下がり銘柄数 |
| 3 | 新高値 − 新安値（ネット） | ブレッドス | Greed | 1/12 | 東証 新高値/新安値銘柄数 |
| 4 | 日経VI | ボラティリティ | **Fear（反転）** | 1/6 | JPX / 大阪取引所 公式 |
| 5 | 日経225オプション Put/Call レシオ | ヘッジ/ポジショニング | **Fear（反転）** | 1/12 | **J-Quants** オプション四本値 |
| 7 | 空売り比率（東証） | ヘッジ/ポジショニング | **Fear（反転）** | 1/12 | **J-Quants** 業種別空売り比率 |
| 6 | 信用評価損益率（買い方） | レバレッジ/個人心理 | 低いほど Fear | 1/6 | 松井証券「投資指標（店内）」日次 |
| 8 | セーフヘイブン需要（株−債20日リターン差） | 安全資産選好 | Greed | 1/6 | 指数価格 + 10年JGB |

### 加重についての設計判断（仕様 §4.1 の不整合への対応）

仕様 §2 は **8指標**で #7 空売り比率を「ヘッジ需要」次元に置きますが、§4.1 は **6次元**しか
列挙せず、記載どおりに計算すると重みの合計が 1 になりません（`2×1/12 + 6×1/6 = 7/6`）。
本実装では **#5 P/Cレシオ と #7 空売り比率 を同一の「ヘッジ / ポジショニング」次元に束ねて
6次元を維持**する方針で確定しました（Ken 確認済み）。結果、各次元 1/6・次元内2指標は各 1/12
となり合計 1.0 に整合します。次元の割り当ては `engine/config.yaml` の1行で変更できます。

---

## アーキテクチャ

```
engine/                     計算エンジン（Python / pandas）
  config.yaml               ★ 定量設計の単一の調整点（採否・正規化・lookback・加重・アンカー）
  fgi/
    config.py               config 読み込み・検証
    normalize.py            正規化（percentile / anchor）§3
    weights.py              次元バケット均等加重 §4
    compose.py              合成・バンド判定・JSON 整形 §5
    pipeline.py             生値系列 → point-in-time 正規化 → 合成
    fetchers/
      base.py               IndicatorSeries・検証・point-in-time(as_of)
      jquants.py            J-Quants API クライアント（#5 #7 指数価格）
      derive.py             生データ→指標生値の純関数（テスト可能）
    providers.py            real/demo の生値系列を組み立てる
  scripts/run_daily.py      日次ランナー → latest.json / history.json
  tests/                    pytest（正規化・加重・合成・派生・point-in-time）
web/                        フロントエンド（Next.js + Recharts）
  app/                      ページ・レイアウト・スタイル
  components/               Gauge / ComparisonStrip / HistoryChart / IndicatorCard
  public/data/              latest.json / history.json（cron が再生成しコミット）
.github/workflows/
  daily.yml                 日次 cron（再生成→コミット→Vercel が静的配信）
  tests.yml                 push/PR で engine テスト + web ビルド
```

### データフロー

```
fetchers/providers → 生値系列(IndicatorSeries, 公表日インデックス)
  → pipeline（各日付で「その日までに入手可能な値」だけ正規化 = point-in-time 厳守）
  → compose（採用指標のみで重みを再正規化。欠損は中立値で埋めず coverage に記録）
  → latest.json（最新値＋指標内訳） / history.json（合成スコア時系列）
  → web が静的配信
```

---

## セットアップ

### 1. 計算エンジン（Python 3.11+）

```bash
cd engine
pip install -r requirements.txt

# 合成データでパイプラインを通す（フロント表示確認用）
python scripts/run_daily.py --mode demo

# テスト
PYTHONPATH=. pytest -q
```

### 2. フロントエンド（Node 20+）

```bash
cd web
npm install
npm run dev      # http://localhost:3000
npm run build    # 本番ビルド
```

`web/public/data/latest.json` / `history.json` を読み込んで描画します。
初期状態では **サンプル（合成データ）** がコミットされており、UI 上に明示されます。

### 3. J-Quants（Phase 0：契約・APIキー発行）

1. J-Quants の **Standard プラン（月3,300円税込）** に契約。
2. **要確認**：申込画面で「Standard で日経225オプション四本値が取得可能」であることを最終確認。
3. リフレッシュトークン（または登録メール＋パスワード）を取得。
4. ローカルは `engine/.env`（`.env.example` を参照）、CI は **GitHub Secrets** に設定：
   - `JQUANTS_REFRESH_TOKEN`（推奨）、または `JQUANTS_MAIL_ADDRESS` + `JQUANTS_PASSWORD`
5. **APIキーはコードに直書きしない**（環境変数 / Secrets のみ）。

---

## データソースの結線状況（重要）

仕様 §0／§8 の方針に従い、**取得が困難な指標を簡易代替で埋めていません**。
未結線の指標は実行時に `FetchError("要確認: …")` となり、その日の合成から **除外**（`stale`）
され、`coverage` に反映されます（欠損を 50＝中立で埋めない）。

| 指標 | 状態 | 結線に必要な作業 |
| --- | --- | --- |
| #1 モメンタム | ✅ 実装済（J-Quants 指数 or stooq から計算） | J-Quants 契約 or stooq 到達確認 |
| #2 騰落レシオ | ⏳ 未結線 | 東証 値上がり/値下がり銘柄数のソース確認（株探/日経・**ToS/robots 要確認**） |
| #3 新高値新安値 | ⏳ 未結線 | 東証 新高値/新安値銘柄数のソース確認 |
| #4 日経VI | ⏳ 未結線 | JPX/大阪取引所 公式 CSV/Excel の結線 |
| #5 P/Cレシオ | ⏳ J-Quants 待ち | **J-Quants 契約・APIキー**（オプション四本値の出来高から算出） |
| #7 空売り比率 | ⏳ J-Quants 待ち | **J-Quants 契約・APIキー**（業種別空売り比率） |
| #6 信用評価損益率 | ⏳ 未結線 | 松井証券「投資指標（店内）」日次値の **ToS/robots 確認**・スクレイプ or ヒストリカル Excel |
| #8 セーフヘイブン | ⏳ 未結線 | 10年JGB トータルリターン系列のソース確認 |

> 各 provider（`engine/fgi/providers.py`）を実データ取得に差し替えると、その指標が
> 自動的に合成へ加わります。**スクレイプ対象は各サイトの ToS・robots を確認**し、取得頻度は
> 日次に抑えてください。規約上の懸念があれば代替ソースを Ken に確認すること。

### J-Quants クライアントの結線メモ
`engine/fgi/fetchers/jquants.py` の `index_ohlc` / `index_option_ohlc` / `short_selling_ratio`
は **エンドポイント名・カラム名・`PutCallDivision` の値の意味**を契約後の API ドキュメントで
確認して微調整する必要があります（コード内に「要確認」コメントあり）。

---

## 正規化方式（§3）

- **percentile（既定）**：直近 `lookback_days`（既定 252＝約1年）のローリング・パーセンタイル順位を
  0〜100 に。分布を仮定せず外れ値に頑健。
- **anchor**：歴史的閾値を持つ指標（騰落レシオ・信用評価損益率）に固定アンカーで区分線形写像。
  例（信用評価損益率）：`-30%→0` / `-20%→20` / `-10%→50` / `0%→100`、境界外はクリップ。
- **方向**：`inverted: true` の指標（日経VI・P/Cレシオ・空売り比率）は正規化後に `100 - score`。
- **point-in-time 厳守**：公表ラグのある指標は実公表日を基準にし、未来情報を混入させない。

すべて `config.yaml` で調整可能（**Python ロジックを変更せずに定量設計を変えられる**）。

---

## デプロイ（Vercel）

1. リポジトリを Vercel に接続し、**Root Directory = `web`** を指定。
2. フレームワークは Next.js（自動検出）。ビルドは `npm run build`。
3. `web/public/data/*.json` は静的配信。日次 cron が再生成・コミットすると Vercel が再デプロイ。

## 日次運用（GitHub Actions）

- `.github/workflows/daily.yml` が **JST 06:00（UTC 21:00）月〜金** に実行。
- `python scripts/run_daily.py --mode real` で再生成 → 差分があれば `web/public/data` をコミット。
- J-Quants 契約・データソース結線が完了するまでは coverage が低い状態になります
  （未結線指標は stale）。手動実行（`workflow_dispatch`）で `demo` も選べます。

---

## 注意・免責

- データ品質を最優先。各 fetcher は取得値のレンジ・型・鮮度を検証し、異常時はその指標を
  当日合成から除外（`stale`）します。**欠損を中立値で埋めません。**
- バックフィル時に「その日時点で入手不可能だったデータ」を使いません（point-in-time）。
- 本指標は情報提供目的の自作指標であり、投資助言ではありません。

## 今後（v2 候補・初版スコープ外）

- 投資主体別売買動向（海外投資家ネット買い・週次）／サイコロジカルライン／NT倍率変化
- 正規化後8指標の**相関チェック**（次元横断の冗長性確認）→ 必要なら ERC 等のオーバーレイ
- バックテスト最適化（過剰最適化に注意し in-sample/out-of-sample 分割必須）
