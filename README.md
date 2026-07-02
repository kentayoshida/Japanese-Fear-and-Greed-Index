# 日本版 Fear & Greed Index

日本株式市場の投資家心理を、複数の独立した市場指標から **0〜100 の単一スコア**に
合成する自作インデックスです。CNN の Fear & Greed Index と同型の設計思想（複数指標を
正規化して合成）を、**日本市場に最適化した指標構成・一次データソース**で実装します。

**TOPIX版**と**日経225版**の2版を同時に算出し、Web トップのタブで切り替えられます。

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
| 1 | 株価指数 vs 125日線乖離率 | モメンタム | Greed | 1/6 | TOPIX=J-Quants(0000) / 日経225=日経公式CSV |
| 2 | 騰落レシオ（東証プライム・25日） | ブレッドス | Greed | 1/12 | **J-Quants** 全銘柄終値から集計 |
| 3 | 新高値 − 新安値（ネット） | ブレッドス | Greed | 1/12 | **J-Quants** 全銘柄終値の52週高安 |
| 4 | 日経VI | ボラティリティ | **Fear（反転）** | 1/6 | 日経公式 日次CSV |
| 5 | 日経225オプション Put/Call レシオ | ヘッジ/ポジショニング | **Fear（反転）** | 1/12 | **J-Quants** オプション四本値（出来高） |
| 7 | 空売り比率（東証） | ヘッジ/ポジショニング | **Fear（反転）** | 1/12 | **J-Quants** 業種別空売り比率 |
| 6 | 信用評価損益率（買い方） | レバレッジ/個人心理 | 低いほど Fear | 1/6 | 松井証券「投資指標（店内）」+ J-Quants 週次信用買い残（三層構成・後述） |
| 8 | セーフヘイブン需要（株−債20日リターン差） | 安全資産選好 | Greed | 1/6 | 株価指数（版別）＋ 国債ETF(2510) 調整後終値 |

株式指数レッグ（**#1 モメンタム**・**#8 セーフヘイブンの株式側**）だけが版ごとに変わり、
市場全体系の #2〜#7 は全版共通です。

### 加重についての設計判断（仕様 §4.1 の不整合への対応）

仕様 §2 は **8指標**で #7 空売り比率を「ヘッジ需要」次元に置きますが、§4.1 は **6次元**しか
列挙せず、記載どおりに計算すると重みの合計が 1 になりません（`2×1/12 + 6×1/6 = 7/6`）。
本実装では **#5 P/Cレシオ と #7 空売り比率 を同一の「ヘッジ / ポジショニング」次元に束ねて
6次元を維持**する方針で確定しました（Ken 確認済み）。採用指標のみで**次元レベルの再正規化**
（§4.1b）を行うため、一部指標が stale でも合計は常に 1.0 に整合します。

### #6 信用評価損益率の三層構成（仕様 §2）

松井証券の「投資指標（店内）」は**最新営業日の1点**しか公開しないため、過去データを
以下の三層で補完します。

- **tier-1（正）**：松井ページを Playwright で描画し、買い方の評価損益率(%)を取得（最新日）。
  リトライ付き（試行ごとに待ち時間を延長）。取得は日次1回に限定（ToS 準拠）。
- **tier-2（近似）**：J-Quants `/markets/margin-interest` の**週次信用買い残(LongVol)**を全銘柄
  合算し、**在庫平均コスト法**で平均建値（指数水準）を推定 → 指数日次終値で含み損益率を MTM
  近似（過去日を日次補完）。
- **tier-3（較正）**：重複日で tier-2 を tier-1 にオフセット較正し、実測がある日は実測で上書き。

松井が一時的に取得できなくても tier-2 が、tier-2 が組めなくても tier-1 が指標を維持します。

---

## アーキテクチャ

```
engine/                     計算エンジン（Python / pandas）
  config.yaml               ★ 定量設計の単一の調整点（採否・正規化・lookback・加重・版）
  fgi/
    config.py               config 読み込み・検証・版(variant)展開
    normalize.py            正規化（percentile / anchor）§3
    weights.py              次元レベル再正規化の加重 §4.1b
    compose.py              合成・バンド判定・JSON 整形 §5
    pipeline.py             生値系列 → point-in-time 正規化 → 合成
    fetchers/
      base.py               IndicatorSeries・検証・point-in-time(as_of)
      jquants.py            J-Quants API v2 クライアント（指数/オプション/空売り/週次信用残/全銘柄終値）
      matsui.py             #6 松井スクレイプ（Playwright・リトライ）
      derive.py             生データ→指標生値の純関数（テスト可能。MTM近似含む）
    providers.py            real/demo の生値系列を版ごとに組み立てる
  scripts/run_daily.py      日次ランナー → 版別 latest/history + variants.json
  tests/                    pytest（正規化・加重・合成・派生・MTM・point-in-time・松井パース）
web/                        フロントエンド（Next.js + Recharts）
  app/                      ページ（版切替タブ）・レイアウト・スタイル（CNN風ライトテーマ）
  components/               Gauge / MiniGauge / ComparisonStrip / HistoryChart / IndicatorCard
  public/data/              変動JSON（cron が再生成しコミット）
    latest.json / history.json            既定版(TOPIX)。後方互換
    latest.<version>.json / history.<version>.json   版別
    variants.json                         版一覧（タブ生成用）
    series/                               生値系列の増分キャッシュ（週次信用残・松井実測 等）
.github/workflows/
  daily.yml                 日次 cron（再生成→コミット→main へ push→Vercel が静的配信）
  tests.yml                 push/PR で engine テスト + web ビルド
```

### データフロー

```
providers（版ごと） → 生値系列(IndicatorSeries, 公表日インデックス)
  → pipeline（各日付で「その日までに入手可能な値」だけ正規化 = point-in-time 厳守）
  → compose（採用指標のみで重みを再正規化。欠損は中立値で埋めず coverage に記録）
  → 版別 latest/history JSON + variants.json
  → web が静的配信（タブで版を切替）
```

---

## セットアップ

### 1. 計算エンジン（Python 3.11+）

```bash
cd engine
pip install -r requirements.txt
python -m playwright install --with-deps chromium   # #6 松井の描画用

# 合成データでパイプラインを通す（フロント表示確認用・ネットワーク不要）
python scripts/run_daily.py --mode demo

# 実データ（要 J-Quants APIキー）
JQUANTS_API_KEY=xxxx python scripts/run_daily.py --mode real

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

`variants.json` を読んでタブを生成し、選択版の `latest.<version>.json` /
`history.<version>.json` を描画します（マニフェスト未生成時は `latest.json` にフォールバック）。

### 3. J-Quants（API v2）

- v2 は **APIキー方式**（`x-api-key` ヘッダー・有効期限なし・無人運用向き）。
- ダッシュボードで発行した APIキーを、ローカルは環境変数、CI は **GitHub Secrets** に設定：
  - `JQUANTS_API_KEY`（推奨） … 後方互換で `JQUANTS_REFRESH_TOKEN` 名でも可
- **APIキーはコードに直書きしない**（環境変数 / Secrets のみ）。
- 指数(0000=TOPIX)・日経225オプション四本値・業種別空売り比率・週次信用取引残高
  （`/markets/margin-interest`）・全銘柄日次終値を使用します。

---

## データソースの結線状況

仕様 §0／§8 の方針に従い、**取得が困難な指標を簡易代替で埋めていません**。
取得不能な指標はその日の合成から **除外**（`stale`）され、`coverage` に反映されます
（欠損を 50＝中立で埋めない）。

| 指標 | 状態 | 備考 |
| --- | --- | --- |
| #1 モメンタム | ✅ 稼働 | TOPIX=J-Quants / 日経225=日経公式CSV |
| #2 騰落レシオ | ✅ 稼働 | 全銘柄終値の前日比を日次キャッシュ（初回は数回で25日窓充填） |
| #3 新高値新安値 | ⏳ 蓄積中 | 52週(252営業日)窓のため終値を数回の実行で充填後に有効化 |
| #4 日経VI | ✅ 稼働 | 日経公式 日次CSV（cp932） |
| #5 P/Cレシオ | ✅ 稼働 | オプション出来高（日次を増分キャッシュ） |
| #7 空売り比率 | ✅ 稼働 | 業種別を市場全体に合算 |
| #6 信用評価損益率 | ✅ 稼働 | 松井(tier-1)＋週次信用残MTM(tier-2)＋較正(tier-3) |
| #8 セーフヘイブン | ✅ 稼働 | 版別株価指数 − 国債ETF(2510) の20日リターン差 |

> #2/#3/#5/#6(tier-2) は API 負荷・レート制限を避けるため `web/public/data/series/` に**増分
> キャッシュ**し、1実行あたり一定件数ずつ過去へ遡って充填します。52週窓の #3 は数週間の
> 日次運用で有効になります。**スクレイプ対象は ToS・robots を確認**し取得は日次1回に抑えます。

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
3. 本番は **`main` ブランチ**を配信。`web/public/data/*.json` は静的配信。

## 日次運用（GitHub Actions）

- `.github/workflows/daily.yml` が **JST 06:00（UTC 21:00）月〜金** に実行。
- `python scripts/run_daily.py --mode real` で全版を再生成 → 差分があれば `web/public/data` を
  コミットし、`fetch + rebase` リトライ付きで push（並行実行の競合に頑健）。
- 手動実行（`workflow_dispatch`）で `demo` も選べます。

---

## 注意・免責

- データ品質を最優先。各 fetcher は取得値のレンジ・型・鮮度を検証し、異常時はその指標を
  当日合成から除外（`stale`）します。**欠損を中立値で埋めません。**
- バックフィル時に「その日時点で入手不可能だったデータ」を使いません（point-in-time）。
- #6 tier-2 は近似（在庫平均コスト法による MTM）です。tier-1 実測が貯まるほど tier-3 較正が
  効いて精度が上がります。
- 本指標は情報提供目的の自作指標であり、投資助言ではありません。

## 今後（v2 候補・初版スコープ外）

- スコアの検証とカリブレーション（実測データ蓄積後）
- 投資主体別売買動向（海外投資家ネット買い・週次）／サイコロジカルライン／NT倍率変化
- 正規化後8指標の**相関チェック**（次元横断の冗長性確認）
- バックテスト（過剰最適化に注意し in-sample/out-of-sample 分割必須）
