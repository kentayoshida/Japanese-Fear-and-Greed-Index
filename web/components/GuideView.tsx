"use client";

// 解説（README）ビュー（日本語 / English）。指数の考え方・各指標・正規化・版・#6三層を解説。

import { ZONES, zoneLabel } from "@/lib/fgi";
import { useLang, Lang } from "@/lib/i18n";

type Bi = { ja: string; en: string };
type Doc = { no: number; name: Bi; dim: Bi; measures: Bi; source: Bi; calc: Bi; high: Bi };

const INDICATORS: Doc[] = [
  {
    no: 1,
    name: { ja: "株価指数 vs 125日移動平均の乖離率", en: "Stock index vs its 125-day moving average" },
    dim: { ja: "モメンタム", en: "Market Momentum" },
    measures: { ja: "相場の「勢い」。株価指数が中期のトレンド（125日移動平均＝約半年の平均値）からどれだけ上/下に離れているか。", en: "Market momentum: how far the index sits above or below its medium-term trend (the 125-day moving average, ~six months)." },
    source: { ja: "TOPIX版=J-Quants の指数四本値、日経225版=日経公式の日次CSV。", en: "TOPIX version: J-Quants index OHLC. Nikkei 225 version: Nikkei's official daily CSV." },
    calc: { ja: "乖離率(%) = (当日終値 − 125日移動平均) ÷ 125日移動平均 × 100。", en: "Deviation (%) = (close − 125-day MA) ÷ 125-day MA × 100." },
    high: { ja: "プラスに大きい＝平均より大きく上＝強気（Greed）。マイナス＝弱気（Fear）。", en: "Large positive = well above the average = greed. Negative = fear." },
  },
  {
    no: 2,
    name: { ja: "騰落レシオ（東証プライム・25日）", en: "Advance/decline ratio (Prime, 25-day)" },
    dim: { ja: "ブレッドス（市場の幅）", en: "Breadth" },
    measures: { ja: "上昇している銘柄がどれだけ「広く」多いか。一部の大型株だけでなく市場全体が上がっているかを見る。25日累積のため平滑化された「市場の幅」の指標で（本家CNNのブレッドスに相当）、動きは緩やか。直近の機敏な変化は #3 が担う。", en: "How broadly stocks are advancing — whether the whole market, not just a few large caps, is rising. As a 25-day cumulative measure it is a smoothed 'breadth' gauge (like CNN's Stock Price Breadth) and moves slowly; the responsive day-to-day signal is #3." },
    source: { ja: "J-Quants の全銘柄終値から、日々の値上がり/値下がり銘柄数を集計。", en: "Daily advancers/decliners tallied from all-issue closes via J-Quants." },
    calc: { ja: "直近25営業日の「値上がり銘柄数の合計 ÷ 値下がり銘柄数の合計 × 100」。120%超で過熱、70%割れで底値圏の目安。", en: "25-day sum of advancers ÷ sum of decliners × 100. Above ~120% suggests overheating; below 70% a bottoming zone." },
    high: { ja: "高い＝広く買われている＝強気。ただし過熱（買われ過ぎ）のサインにもなる。", en: "High = broadly bought = greed, though it can also flag an overbought market." },
  },
  {
    no: 3,
    name: { ja: "新高値 − 新安値（東証全体・ネット）", en: "Net new 52-week highs and lows (TSE)" },
    dim: { ja: "ブレッドス（市場の幅）", en: "Breadth" },
    measures: { ja: "52週高値をつけた銘柄と安値をつけた銘柄の差。相場の「地力」の強さ。騰落レシオ(#2)より日々の変化に機敏で、直近の地合いをよく映す（本家CNNの Stock Price Strength に相当）。", en: "The gap between stocks hitting 52-week highs and those hitting lows — the market's underlying strength. More responsive day to day than #2, so it better reflects the latest tone (like CNN's Stock Price Strength)." },
    source: { ja: "J-Quants の全銘柄終値の52週（約245営業日）高値・安値から判定。", en: "Judged from 52-week (~245 trading-day) highs/lows of all-issue closes via J-Quants." },
    calc: { ja: "新高値をつけた銘柄数 − 新安値をつけた銘柄数（ネット）。", en: "Number of new highs − number of new lows (net)." },
    high: { ja: "プラス＝新高値銘柄が多い＝強い相場（Greed）。マイナス＝崩れている（Fear）。", en: "Positive = more new highs = a strong market (greed). Negative = weakening (fear)." },
  },
  {
    no: 4,
    name: { ja: "日経VI（ボラティリティ・インデックス）", en: "Nikkei Volatility Index (VI)" },
    dim: { ja: "ボラティリティ", en: "Volatility" },
    measures: { ja: "投資家が今後1か月の値動きの荒さ（不安）をどれだけ見込んでいるか。いわゆる「恐怖指数」の日本版。", en: "How much turbulence (anxiety) investors expect over the next month — Japan's version of the 'fear gauge.'" },
    source: { ja: "日経公式の日経VI 日次CSV。", en: "Nikkei's official daily VI CSV." },
    calc: { ja: "日経225オプション価格から算出される予想変動率（％）。値そのものを使用。", en: "Implied volatility (%) derived from Nikkei 225 option prices; the value itself is used." },
    high: { ja: "高い＝不安が大きい＝Fear。そのため本指標は反転して合成（高VI→低スコア）。", en: "High = more anxiety = fear, so this indicator is inverted (high VI → low score)." },
  },
  {
    no: 5,
    name: { ja: "日経225オプション Put/Call レシオ", en: "Nikkei 225 options put/call ratio" },
    dim: { ja: "ヘッジ / ポジショニング", en: "Hedging & Positioning" },
    measures: { ja: "下落に備える「保険」（プット）がどれだけ買われているか。投資家の警戒度。", en: "How much downside 'insurance' (puts) is being bought — investors' level of caution." },
    source: { ja: "J-Quants の日経225オプション四本値（出来高）。", en: "Nikkei 225 option OHLC (volume) via J-Quants." },
    calc: { ja: "その日のプット出来高 ÷ コール出来高。", en: "Daily put volume ÷ call volume." },
    high: { ja: "高い＝下落ヘッジ需要が強い＝Fear。反転して合成。", en: "High = strong downside-hedging demand = fear. Inverted in the composite." },
  },
  {
    no: 7,
    name: { ja: "空売り比率（東証）", en: "Short-selling ratio (TSE)" },
    dim: { ja: "ヘッジ / ポジショニング", en: "Hedging & Positioning" },
    measures: { ja: "売買のうち「空売り（下落に賭ける売り）」が占める割合。弱気姿勢の強さ。", en: "The share of trading that is short selling (bets on falling prices) — how bearish positioning is." },
    source: { ja: "J-Quants の業種別空売り比率を市場全体に合算。", en: "Sector short-selling ratios via J-Quants, aggregated market-wide." },
    calc: { ja: "(規制あり空売り + 規制なし空売り) ÷ (実売り + 空売り合計) × 100。", en: "(restricted + unrestricted short selling) ÷ (real selling + total short selling) × 100." },
    high: { ja: "高い＝弱気/ヘッジが強い＝Fear。反転して合成。", en: "High = stronger bearish/hedging stance = fear. Inverted in the composite." },
  },
  {
    no: 6,
    name: { ja: "信用評価損益率（買い方）", en: "Margin trading P/L ratio (long)" },
    dim: { ja: "レバレッジ / 個人心理", en: "Leverage & Retail Sentiment" },
    measures: { ja: "信用取引で株を買っている個人投資家が、平均でどれだけ含み益/含み損かの割合。個人の楽観・悲観の温度計。", en: "The average unrealized profit/loss of retail investors holding stocks on margin — a thermometer of retail optimism vs. pessimism." },
    source: { ja: "松井証券「投資指標（店内）」の最新値（正）＋ J-Quants の週次信用買い残から推計した過去分（三層構成・下記）。", en: "Matsui Securities' latest published value (authoritative) plus history estimated from J-Quants weekly margin balances (three-tier design, below)." },
    calc: { ja: "評価損益率(%)。おおむね 0%近辺で楽観、−20%以下で強い悲観。アンカー（-30→0, -20→20, -10→50, 0→100）で0-100化。", en: "P/L ratio (%). Roughly 0% is optimistic; −20% or lower is strong pessimism. Mapped to 0–100 via anchors (−30→0, −20→20, −10→50, 0→100)." },
    high: { ja: "高い（含み損が浅い/含み益）＝個人が強気。低い（含み損が深い）＝個人の恐怖。", en: "Higher (shallow loss or a gain) = retail greed. Lower (deep loss) = retail fear." },
  },
  {
    no: 8,
    name: { ja: "セーフヘイブン需要（株式 − 債券 20日リターン差）", en: "Safe-haven demand (stock − bond 20-day return)" },
    dim: { ja: "安全資産選好", en: "Safe-Haven Demand" },
    measures: { ja: "お金が「リスク資産（株）」と「安全資産（債券）」のどちらに向かっているか。", en: "Whether money is flowing toward risk assets (stocks) or safe assets (bonds)." },
    source: { ja: "版の株価指数 と 国債ETF(2510) の調整後終値。", en: "The version's stock index and the JGB ETF (2510) adjusted closes." },
    calc: { ja: "株式の20日リターン − 債券の20日リターン（％）。", en: "Stock 20-day return − bond 20-day return (%)." },
    high: { ja: "プラス＝株が債券に勝っている＝リスク選好（Greed）。マイナス＝安全資産へ逃避（Fear）。", en: "Positive = stocks beating bonds = risk-on (greed). Negative = flight to safety (fear)." },
  },
];

const G: Record<Lang, any> = {
  ja: {
    eyebrow: "解説",
    title: "Fear & Greed Index の読み方",
    lead: "相場は最終的に「恐怖（Fear）」と「強欲（Greed）」という2つの感情で動く、という考え方があります。本指数は、日本株式市場のさまざまなデータを 0〜100 の単一スコアにまとめ、いま市場心理がどちらに傾いているかを一目で分かるようにしたものです。",
    hRead: "スコアの読み方",
    pRead: "スコアは 0（極度の恐怖）〜 100（極度の貪欲）。一般に、極端な恐怖は「売られ過ぎ」の目安、極端な貪欲は「買われ過ぎ」の目安として、逆張りの参考に使われます（＝みんなが怖がっている時こそ好機、という逆張り思想）。",
    hInd: "8つの指標",
    pInd: "スコアは 6つの「心理次元」（モメンタム／市場の幅／ボラティリティ／ヘッジ・ポジショニング／レバレッジ・個人心理／安全資産選好）に均等な重みを置き、各次元の指標を合成しています。一部の指標が取得できない日は、その指標を除いて残りで重みを再配分します（欠損を50＝中立で埋めません）。",
    lblMeasures: "何を測る？",
    lblSource: "データソース",
    lblCalc: "計算方法",
    lblHigh: "高い/低いの意味",
    hNorm: "スコア化（正規化）の考え方",
    norm: [
      "パーセンタイル方式：直近約1年（245〜252営業日）の中で、今日の値が何％の位置にあるかで 0〜100 に変換。分布の形を仮定せず外れ値に強い方式です。",
      "アンカー方式：騰落レシオや信用評価損益率のように「経験的な目安（しきい値）」がある指標は、固定の基準点（例：信用評価損益率 −30%→0点、0%→100点）で変換します。",
      "反転：日経VI・P/Cレシオ・空売り比率は「高い＝恐怖」なので、スコア化後に100から引いて向きをそろえます。",
      "point-in-time（先読み防止）：過去の各日について、その日までに実際に入手できたデータだけで計算します。未来の情報は使いません。",
    ],
    hVer: "TOPIX版 と 日経225版",
    pVer: "相場の「勢い（#1）」と「安全資産選好（#8）」に使う株価指数だけを、TOPIX または 日経平均に差し替えた2つの版を用意しています。値動きの幅が広い日経225と、市場全体を時価総額加重で表すTOPIXでは、同じ日でもスコアが異なることがあります。その他の指標（市場の幅・ボラティリティ・ヘッジ・個人心理）は両版で共通です。",
    hTier: "#6 信用評価損益率の三層構成",
    pTier: "#6 は個人心理をよく映す指標ですが、公開値は「最新日の1点」しか手に入りません。そこで過去分を次の三層で補います。",
    tiers: [
      "tier-1（正）：松井証券のページから最新営業日の実測値を取得。",
      "tier-2（近似）：市場全体の週次「信用買い残高」と株価指数から、平均建値を推計して日々の含み損益率を近似（在庫平均コスト法によるマーク・トゥ・マーケット）。",
      "tier-3（較正）：実測値が得られた日で近似値のズレを補正します。実測点が貯まるほど精度が上がります。",
    ],
    disclaimer: "⚠ 本指標は情報提供・学習目的の自作指標であり、投資助言ではありません。売買の判断はご自身の責任で行ってください。",
  },
  en: {
    eyebrow: "Guide",
    title: "How to read the Fear & Greed Index",
    lead: "There is a view that markets are ultimately driven by two emotions — fear and greed. This index gathers a range of Japanese-market data into a single 0–100 score so you can see at a glance which way sentiment is leaning.",
    hRead: "Reading the score",
    pRead: "The score runs from 0 (Extreme Fear) to 100 (Extreme Greed). Broadly, extreme fear is used as a rough 'oversold' signal and extreme greed as an 'overbought' one — a contrarian reference (the idea that opportunity appears when everyone is fearful).",
    hInd: "The eight indicators",
    pInd: "The score weights six psychological dimensions equally (momentum, breadth, volatility, hedging & positioning, leverage & retail sentiment, and safe-haven demand) and composes the indicators within each. On days when an indicator cannot be fetched, it is dropped and the weights are re-distributed over the rest (missing values are never filled with a neutral 50).",
    lblMeasures: "What it measures",
    lblSource: "Data source",
    lblCalc: "How it's calculated",
    lblHigh: "What high / low means",
    hNorm: "How values become a score (normalization)",
    norm: [
      "Percentile method: converts today's value to 0–100 by its position within roughly the past year (245–252 trading days). It assumes no particular distribution and is robust to outliers.",
      "Anchor method: indicators with empirical thresholds (e.g. the advance/decline ratio, margin P/L ratio) are mapped through fixed anchor points (e.g. margin P/L −30%→0, 0%→100).",
      "Inversion: for the Nikkei VI, put/call ratio and short-selling ratio, 'high = fear,' so the score is subtracted from 100 to align direction.",
      "Point-in-time: each past day is computed using only data that was actually available then. No future information is used.",
    ],
    hVer: "TOPIX vs Nikkei 225 versions",
    pVer: "Two versions differ only in the stock index used for momentum (#1) and safe-haven demand (#8) — TOPIX or the Nikkei 225. Because the wide-moving Nikkei 225 and the market-cap-weighted, whole-market TOPIX contribute differently, the score can differ on the same day. All other indicators (breadth, volatility, hedging, retail sentiment) are shared.",
    hTier: "The three-tier design of #6 (margin P/L ratio)",
    pTier: "#6 reflects retail sentiment well, but only the single latest value is published. Past values are therefore filled in three tiers:",
    tiers: [
      "tier-1 (authoritative): the latest business-day value scraped from Matsui Securities' page.",
      "tier-2 (approximation): from the market-wide weekly margin-buy balance and the stock index, an average entry price is estimated and the daily unrealized P/L is approximated (mark-to-market via inventory average cost).",
      "tier-3 (calibration): on days with a measured value, the approximation's offset is corrected. Accuracy improves as measured points accumulate.",
    ],
    disclaimer: "⚠ This is an independent index for information and educational purposes, not investment advice. Trade at your own responsibility.",
  },
};

export default function GuideView() {
  const { lang } = useLang();
  const g = G[lang];
  return (
    <div className="guide">
      <header className="guide__hero">
        <div className="hero__eyebrow">{g.eyebrow}</div>
        <h1 className="guide__title">{g.title}</h1>
        <p className="guide__lead">{g.lead}</p>
      </header>

      <section className="guide__section">
        <h2 className="guide__h2">{g.hRead}</h2>
        <p className="guide__p">{g.pRead}</p>
        <div className="guide__zones">
          {ZONES.map((z) => (
            <div className="guide__zone" key={z.key}>
              <span className="guide__zone-swatch" style={{ background: z.color }} />
              <span className="guide__zone-range">
                {z.min}–{z.max}
              </span>
              <span className="guide__zone-label">{zoneLabel(z, lang)}</span>
            </div>
          ))}
        </div>
      </section>

      <section className="guide__section">
        <h2 className="guide__h2">{g.hInd}</h2>
        <p className="guide__p">{g.pInd}</p>
        <div className="guide__cards">
          {INDICATORS.map((d) => (
            <article className="guide-card" key={d.no}>
              <div className="guide-card__head">
                <span className="guide-card__no">#{d.no}</span>
                <div>
                  <h3 className="guide-card__name">{d.name[lang]}</h3>
                  <span className="guide-card__dim">{d.dim[lang]}</span>
                </div>
              </div>
              <dl className="guide-card__dl">
                <dt>{g.lblMeasures}</dt>
                <dd>{d.measures[lang]}</dd>
                <dt>{g.lblSource}</dt>
                <dd>{d.source[lang]}</dd>
                <dt>{g.lblCalc}</dt>
                <dd>{d.calc[lang]}</dd>
                <dt>{g.lblHigh}</dt>
                <dd>{d.high[lang]}</dd>
              </dl>
            </article>
          ))}
        </div>
      </section>

      <section className="guide__section">
        <h2 className="guide__h2">{g.hNorm}</h2>
        <ul className="guide__ul">
          {g.norm.map((s: string, i: number) => (
            <li key={i}>{s}</li>
          ))}
        </ul>
      </section>

      <section className="guide__section">
        <h2 className="guide__h2">{g.hVer}</h2>
        <p className="guide__p">{g.pVer}</p>
      </section>

      <section className="guide__section">
        <h2 className="guide__h2">{g.hTier}</h2>
        <p className="guide__p">{g.pTier}</p>
        <ol className="guide__ol">
          {g.tiers.map((s: string, i: number) => (
            <li key={i}>{s}</li>
          ))}
        </ol>
      </section>

      <p className="guide__disclaimer">{g.disclaimer}</p>
    </div>
  );
}
