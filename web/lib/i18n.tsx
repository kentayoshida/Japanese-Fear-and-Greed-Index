"use client";

// 多言語対応（日本語 / English）。LangContext と翻訳辞書。

import { createContext, useContext } from "react";

export type Lang = "ja" | "en";

export const LangContext = createContext<{ lang: Lang; setLang: (l: Lang) => void }>({
  lang: "ja",
  setLang: () => {},
});
export const useLang = () => useContext(LangContext);

type Bi = { ja: string; en: string };

// ---- 共通UI文字列 ----
export const UI: Record<Lang, Record<string, string>> = {
  ja: {
    brand: "恐怖と強欲指数",
    navDashboard: "ダッシュボード",
    navGuide: "指標の解説",
    heroEyebrow: "恐怖と強欲指数（日本株版）",
    heroTitle: "いま市場を動かしている感情は？",
    sample: "⚠ これはサンプル（合成データ）です。実データソース（J-Quants 等）を結線すると本番値に切り替わります。",
    overview: "概要",
    timeline: "推移",
    asOf: "基準日",
    coverage: "採用指標",
    updated: "最終更新",
    comparePrev: "前営業日",
    compareWeek: "1週間前",
    compareMonth: "1か月前",
    compareYear: "1年前",
    noData: "データなし",
    historyTitle: "ヒストリカル推移",
    overlayIndex: "指数を重ねる",
    fgScore: "F&G スコア",
    annGreed: "▲ 極度の貪欲",
    annFear: "▼ 極度の恐怖",
    indicatorsUsed: "採用指標",
    chartNote: "※ 全8指標がそろう前の期間は、その時点で入手できた少数の指標で算出しています（各点の採用指標数はツールチップに表示）。指標が蓄積するほど本来の合成に近づきます。",
    cardValue: "生値",
    cardWeight: "重み",
    cardAsOf: "基準日",
    cardFetched: "取得",
    chartAccum: "データ蓄積中…",
    disclaimer: "本指標は情報提供目的の自作指標であり、投資助言ではありません。",
    footerUpdated: "最終更新",
    loading: "読み込み中…",
    loadError: "データを読み込めませんでした。",
    language: "Language",
    faqTitle: "よくある質問",
  },
  en: {
    brand: "Fear & Greed Index",
    navDashboard: "Dashboard",
    navGuide: "Guide",
    heroEyebrow: "Fear & Greed Index — Japan",
    heroTitle: "What emotion is driving the market now?",
    sample: "⚠ This is sample (synthetic) data. Connecting live sources (J-Quants, etc.) switches to production values.",
    overview: "Overview",
    timeline: "Timeline",
    asOf: "As of",
    coverage: "Indicators",
    updated: "Last updated",
    comparePrev: "Previous close",
    compareWeek: "1 week ago",
    compareMonth: "1 month ago",
    compareYear: "1 year ago",
    noData: "No data",
    historyTitle: "Fear & Greed Over Time",
    overlayIndex: "Overlay index",
    fgScore: "F&G Score",
    annGreed: "▲ Extreme Greed",
    annFear: "▼ Extreme Fear",
    indicatorsUsed: "Indicators",
    chartNote: "Note: before all 8 indicators are available, scores are computed from the few indicators available at the time (count shown in the tooltip). Scores converge to the full composite as data accumulates.",
    cardValue: "Value",
    cardWeight: "Weight",
    cardAsOf: "As of",
    cardFetched: "Fetched",
    chartAccum: "Accumulating data…",
    disclaimer: "This is an independent, information-only index and not investment advice.",
    footerUpdated: "Last updated",
    loading: "Loading…",
    loadError: "Failed to load data.",
    language: "Language",
    faqTitle: "Frequently asked questions",
  },
};

export function t(lang: Lang, key: string): string {
  return UI[lang][key] ?? UI.ja[key] ?? key;
}

// 版（バリアント）の表示名
export const VARIANT_LABEL: Record<string, Bi> = {
  nikkei225: { ja: "日経225", en: "Nikkei 225" },
  topix: { ja: "TOPIX", en: "TOPIX" },
};
export function variantLabel(key: string, fallback: string, lang: Lang): string {
  return VARIANT_LABEL[key]?.[lang] ?? fallback;
}
// JAは「◯◯版」、ENはそのまま
export function variantTab(key: string, fallback: string, lang: Lang): string {
  const base = variantLabel(key, fallback, lang);
  return lang === "ja" ? `${base}版` : base;
}

// 「N個の構成指標」/ "N Fear & Greed Indicators"
export function indicatorsHeading(n: number, lang: Lang): string {
  return lang === "ja" ? `${n}個の構成指標` : `${n} Fear & Greed Indicators`;
}

// ---- 心理次元 ----
export const DIM: Record<string, Bi> = {
  momentum: { ja: "モメンタム", en: "Market Momentum" },
  breadth: { ja: "ブレッドス", en: "Stock Price Breadth" },
  volatility: { ja: "ボラティリティ", en: "Market Volatility" },
  hedge_positioning: { ja: "ヘッジ / ポジショニング", en: "Hedging & Positioning" },
  leverage: { ja: "レバレッジ / 個人心理", en: "Leverage & Retail Sentiment" },
  safe_haven: { ja: "安全資産選好", en: "Safe-Haven Demand" },
};

// ---- 指標名（EN は版に依存しない汎用名） ----
export const IND_NAME: Record<string, string> = {
  momentum_125dma: "Stock index vs its 125-day moving average",
  advance_decline_25: "Advance/decline ratio (Prime, 25-day)",
  new_high_low: "Net new 52-week highs and lows (TSE)",
  nikkei_vi: "Nikkei Volatility Index (VI)",
  put_call_ratio: "Nikkei 225 options put/call ratio",
  short_selling_ratio: "Short-selling ratio (TSE)",
  margin_pl_ratio: "Margin trading P/L ratio (long)",
  safe_haven: "Safe-haven demand (stock − bond 20-day return)",
};

// ---- チャートのサブタイトル ----
export const IND_SUB: Record<string, Bi> = {
  momentum_125dma: {
    ja: "株価指数の125日移動平均からの乖離率（％）",
    en: "Deviation of the index from its 125-day moving average (%)",
  },
  advance_decline_25: { ja: "騰落レシオ（25日・％）", en: "25-day advance/decline ratio (%)" },
  new_high_low: { ja: "新高値 − 新安値（ネット銘柄数）", en: "Net new highs minus new lows (count)" },
  nikkei_vi: { ja: "日経VI（予想変動率）", en: "Nikkei VI (implied volatility)" },
  put_call_ratio: { ja: "Put/Call レシオ（出来高ベース）", en: "Put/call ratio (by volume)" },
  short_selling_ratio: { ja: "空売り比率（％）", en: "Short-selling ratio (%)" },
  margin_pl_ratio: { ja: "信用評価損益率（買い方・％）", en: "Margin P/L ratio, long side (%)" },
  safe_haven: { ja: "株式 − 債券 20日リターン差（％）", en: "Stock − bond 20-day return difference (%)" },
};

// ---- 指標の説明（2〜3文） ----
export const IND_DESC: Record<string, Bi> = {
  momentum_125dma: {
    ja: "株価指数が過去半年(125日)の平均水準からどれだけ上/下に離れているかを見ます。平均より上なら上昇の勢いが強く強気、下なら投資家が慎重になっているサインです。本指数は勢いの鈍化を恐怖、拡大を強欲の signal に使います。",
    en: "Shows how far the index sits above or below its average level over the past ~six months (125 trading days). Above the average signals positive momentum and greed; below it means investors are getting cautious. Slowing momentum is read as fear, growing momentum as greed.",
  },
  advance_decline_25: {
    ja: "値上がり銘柄と値下がり銘柄の数を25日ぶん累積した比率です。一部の大型株だけでなく市場全体が広く買われているかを示します。高いほど強気ですが、120%を超えると過熱（買われ過ぎ）の目安にもなります。本指数では市場の幅を平滑化して捉える指標で（25日累積のため動きは緩やか）、本家CNNのブレッドス指標に相当します。直近の機敏な変化は#3「新高値 − 新安値」が担います。",
    en: "The ratio of advancing to declining stocks accumulated over 25 days. It shows whether the whole market — not just a few large caps — is broadly bid. Higher is more bullish, though above ~120% it can also flag an overheated (overbought) market. In this index it is the smoothed breadth gauge (25-day cumulative, so it moves slowly), analogous to CNN's Stock Price Breadth; the more responsive, day-to-day signal comes from #3 (net new highs minus lows).",
  },
  new_high_low: {
    ja: "年初来（52週）高値をつけた銘柄と安値をつけた銘柄の差です。高値の方が多ければ相場の地力が強く強気、安値が多ければ内部は崩れており弱気を示します。25日累積の騰落レシオ（#2）と違い日々の変化を機敏に映すため、直近の地合いはこちらがよく表します（本家CNNの Stock Price Strength に相当）。",
    en: "The difference between the number of stocks hitting 52-week highs and those hitting 52-week lows. More highs than lows points to underlying strength and greed; more lows signals internal weakness and fear. Unlike the 25-day advance/decline ratio (#2), it reacts quickly day to day, so it better reflects the latest market tone (analogous to CNN's Stock Price Strength).",
  },
  nikkei_vi: {
    ja: "日経平均オプションから算出される今後1か月の予想変動率で、いわゆる恐怖指数です。相場が急落すると跳ね上がり、落ち着くと低下します。高いほど不安が大きく、本指数は上昇を恐怖の signal に使います。",
    en: "Implied volatility for the next month derived from Nikkei 225 options — the market's 'fear gauge.' It spikes when the market sells off and falls when things calm down. Higher readings mean more anxiety, so rising volatility is read as fear.",
  },
  put_call_ratio: {
    ja: "下落に備える保険であるプットが、上昇に賭けるコールに対してどれだけ買われているかの比率です。1を超えると弱気とされ、上昇するほど投資家が神経質になっているサイン。本指数は高い比率を恐怖の signal に使います。",
    en: "How much downside insurance (puts) is being bought relative to upside bets (calls). A ratio above 1 is considered bearish, and a rising ratio shows investors are getting nervous. A higher put/call ratio is read as fear.",
  },
  short_selling_ratio: {
    ja: "売買代金に占める空売り（下落に賭ける売り）の割合です。高いほど弱気・ヘッジ姿勢が強いことを示します。本指数は空売り比率の上昇を恐怖の signal に使います。",
    en: "The share of trading value coming from short selling (bets on falling prices). A higher ratio indicates stronger bearish or hedging positioning, so a rising short-selling ratio is read as fear.",
  },
  margin_pl_ratio: {
    ja: "信用取引で株を買っている個人が平均でどれだけ含み益/含み損かを示します。0%近辺なら楽観、−20%以下は歴史的に強い悲観（逆張り買いの目安）とされます。低いほど個人の恐怖が強い状態です。",
    en: "The average unrealized profit or loss of retail investors holding stocks on margin. Around 0% suggests optimism, while −20% or lower has historically marked strong pessimism (a contrarian buy zone). Lower readings mean stronger retail fear.",
  },
  safe_haven: {
    ja: "株式と債券の直近20日リターンの差です。株が債券に勝っていればお金がリスク資産に向かい強気、債券が勝っていれば安全資産へ逃避しており弱気。本指数は安全資産需要の高まりを恐怖の signal に使います。",
    en: "The difference in the last 20 days' returns between stocks and bonds. When stocks beat bonds, money is moving into risk assets (greed); when bonds win, investors are fleeing to safety (fear). Rising safe-haven demand is read as fear.",
  },
};

export function pick(bi: Bi | undefined, lang: Lang, fallback = ""): string {
  return bi ? bi[lang] : fallback;
}
