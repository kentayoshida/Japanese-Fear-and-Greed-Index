// 日本版 Fear & Greed Index — 型定義とゾーン/バンドのヘルパー。
// 5ゾーンの配色は仕様 §6.5 に準拠（本家ライブページ参照で微調整可能）。

export type Component = {
  id: string;
  label: string;
  dimension: string;
  raw: number | null;
  score: number | null;
  weight: number;
  inverted: boolean;
  stale: boolean;
  description?: string;
};

export type Latest = {
  as_of: string;
  score: number | null;
  band: string;
  band_label_ja: string;
  coverage: number;
  n_indicators: number;
  lookback_days: number;
  components: Component[];
  generated_at?: string;
  mode?: string;
  sample?: boolean;
  fetch_errors?: Record<string, string>;
  disclaimer?: string;
};

export type HistoryPoint = {
  date: string;
  score: number;
  band: string;
  coverage: number;
};

// 版（TOPIX版 / 日経225版）。variants.json のマニフェスト。
export type VariantInfo = {
  key: string;
  label_ja: string;
  default: boolean;
};

export type VariantsManifest = {
  variants: VariantInfo[];
  generated_at?: string;
};

// 5ゾーン定義（§5.1 のバンドと一致）。
export type Zone = {
  key: string;
  labelJa: string;
  min: number;
  max: number;
  color: string;
};

export const ZONES: Zone[] = [
  { key: "extreme-fear", labelJa: "極度の恐怖", min: 0, max: 25, color: "#c0392b" },
  { key: "fear", labelJa: "恐怖", min: 25, max: 45, color: "#e07b1f" },
  { key: "neutral", labelJa: "中立", min: 45, max: 55, color: "#d8b400" },
  { key: "greed", labelJa: "貪欲", min: 55, max: 75, color: "#70bb50" },
  { key: "extreme-greed", labelJa: "極度の貪欲", min: 75, max: 100, color: "#1a9850" },
];

export function zoneForScore(score: number): Zone {
  for (const z of ZONES) {
    if (score >= z.min && score < z.max) return z;
  }
  return ZONES[ZONES.length - 1];
}

export function colorForScore(score: number): string {
  return zoneForScore(score).color;
}

export function labelForScore(score: number): string {
  return zoneForScore(score).labelJa;
}

// 時点比較ストリップ用：history から「N営業日前に最も近い」点を拾う。
export function lookupAtOffset(history: HistoryPoint[], tradingDaysBack: number): HistoryPoint | null {
  if (history.length === 0) return null;
  const idx = history.length - 1 - tradingDaysBack;
  if (idx < 0) return history[0];
  return history[idx];
}

// 各指標の Fear/Greed 寄りラベル（カード表示用）。
export function leanForComponent(c: Component): { text: string; color: string } | null {
  if (c.score === null) return null;
  const z = zoneForScore(c.score);
  return { text: z.labelJa, color: z.color };
}
