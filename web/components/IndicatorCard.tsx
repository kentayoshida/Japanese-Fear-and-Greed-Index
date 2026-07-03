"use client";

// 指標カード（本家CNN型）。2カラム：
//  左＝eyebrow(カテゴリ)＋指標名＋生値ラインチャート(右軸)＋基準日/取得
//  右＝状態バッジ（現在の判定）＋説明文（2〜3文）

import {
  CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { Component, colorForScore, labelForScore } from "@/lib/fgi";

const DIMENSION_LABELS: Record<string, string> = {
  momentum: "モメンタム",
  breadth: "ブレッドス",
  volatility: "ボラティリティ",
  hedge_positioning: "ヘッジ / ポジショニング",
  leverage: "レバレッジ / 個人心理",
  safe_haven: "安全資産選好",
};

// チャートが描く生値の説明（本家の chart subtitle 相当）。
const CHART_SUBTITLE: Record<string, string> = {
  momentum_125dma: "株価指数の125日移動平均からの乖離率（％）",
  advance_decline_25: "騰落レシオ（25日・％）",
  new_high_low: "新高値 − 新安値（ネット銘柄数）",
  nikkei_vi: "日経VI（予想変動率）",
  put_call_ratio: "Put/Call レシオ（出来高ベース）",
  short_selling_ratio: "空売り比率（％）",
  margin_pl_ratio: "信用評価損益率（買い方・％）",
  safe_haven: "株式 − 債券 20日リターン差（％）",
};

// 説明文（日本語オリジナル・2〜3文。何を測り、どちらが恐怖かを平易に）。
const DESCRIPTIONS: Record<string, string> = {
  momentum_125dma:
    "株価指数が過去半年(125日)の平均水準からどれだけ上/下に離れているかを見ます。平均より上なら上昇の勢いが強く強気、下なら投資家が慎重になっているサインです。本指数は勢いの鈍化を恐怖、拡大を強欲の signal に使います。",
  advance_decline_25:
    "値上がり銘柄と値下がり銘柄の数を25日ぶん累積した比率です。一部の大型株だけでなく市場全体が広く買われているかを示します。高いほど強気ですが、120%を超えると過熱（買われ過ぎ）の目安にもなります。",
  new_high_low:
    "年初来(52週)高値をつけた銘柄と安値をつけた銘柄の差です。高値の方が多ければ相場の地力が強く強気、安値が多ければ内部は崩れており弱気を示します。",
  nikkei_vi:
    "日経平均オプションから算出される今後1か月の予想変動率で、いわゆる恐怖指数です。相場が急落すると跳ね上がり、落ち着くと低下します。高いほど不安が大きく、本指数は上昇を恐怖の signal に使います。",
  put_call_ratio:
    "下落に備える保険であるプットが、上昇に賭けるコールに対してどれだけ買われているかの比率です。1を超えると弱気とされ、上昇するほど投資家が神経質になっているサイン。本指数は高い比率を恐怖の signal に使います。",
  short_selling_ratio:
    "売買代金に占める空売り（下落に賭ける売り）の割合です。高いほど弱気・ヘッジ姿勢が強いことを示します。本指数は空売り比率の上昇を恐怖の signal に使います。",
  margin_pl_ratio:
    "信用取引で株を買っている個人が平均でどれだけ含み益/含み損かを示します。0%近辺なら楽観、−20%以下は歴史的に強い悲観（逆張り買いの目安）とされます。低いほど個人の恐怖が強い状態です。",
  safe_haven:
    "株式と債券の直近20日リターンの差です。株が債券に勝っていればお金がリスク資産に向かい強気、債券が勝っていれば安全資産へ逃避しており弱気。本指数は安全資産需要の高まりを恐怖の signal に使います。",
};

function formatFetched(iso?: string): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleString("ja-JP", {
    year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit",
  });
}

function monthTick(d: string): string {
  // "2026-01-15" → "26/01"
  return d.length >= 7 ? d.slice(2, 7).replace("-", "/") : d;
}

function RawTooltip({ active, payload, label }: any) {
  if (!active || !payload || !payload.length) return null;
  const v = payload[0].value;
  return (
    <div className="chart-tooltip">
      <div className="chart-tooltip__date">{label}</div>
      <div className="chart-tooltip__index">
        {typeof v === "number" ? v.toLocaleString(undefined, { maximumFractionDigits: 2 }) : "—"}
      </div>
    </div>
  );
}

function RawChart({ series }: { series: { d: string; v: number | null }[] }) {
  const valid = series.filter((p) => typeof p.v === "number");
  if (valid.length < 2) {
    return <div className="rawchart rawchart--empty">データ蓄積中…</div>;
  }
  return (
    <div className="rawchart">
      <ResponsiveContainer width="100%" height={150}>
        <LineChart data={series} margin={{ top: 6, right: 4, bottom: 0, left: 0 }}>
          <CartesianGrid vertical={false} stroke="#eef0f2" />
          <XAxis
            dataKey="d" tickFormatter={monthTick} minTickGap={44}
            tick={{ fill: "#8a929b", fontSize: 10 }} tickLine={false}
            axisLine={{ stroke: "#e0e0e0" }}
          />
          <YAxis
            orientation="right" domain={["auto", "auto"]} width={46}
            tick={{ fill: "#8a929b", fontSize: 10 }} tickLine={false} axisLine={false}
            tickFormatter={(v: number) => v.toLocaleString(undefined, { maximumFractionDigits: 1 })}
          />
          <Tooltip content={<RawTooltip />} />
          <Line type="monotone" dataKey="v" stroke="#2b6cb0" strokeWidth={1.6}
                dot={false} isAnimationActive={false} connectNulls />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export default function IndicatorCard({
  c,
  generatedAt,
}: {
  c: Component;
  generatedAt?: string;
}) {
  const fetched = formatFetched(generatedAt);
  const series = c.series ?? [];
  const badgeColor = c.score !== null ? colorForScore(c.score) : "#9aa0a6";
  const badgeText = c.score !== null ? labelForScore(c.score) : "データ未取得";

  return (
    <article className={`ind-card ${c.stale ? "is-stale" : ""}`}>
      <div className="ind-card__main">
        <div className="fg-eyebrow">{DIMENSION_LABELS[c.dimension] ?? c.dimension}</div>
        <h3 className="ind-card__title">{c.label}</h3>
        <div className="ind-card__sub">{CHART_SUBTITLE[c.id] ?? ""}</div>
        <RawChart series={series} />
        <div className="ind-card__updated">
          {c.data_date && <span>基準日 {c.data_date}</span>}
          {c.data_date && fetched && <span className="dot">•</span>}
          {fetched && <span>取得 {fetched}</span>}
        </div>
      </div>

      <div className="ind-card__side">
        <span className="ind-badge" style={{ color: badgeColor, borderColor: badgeColor }}>
          {badgeText}
        </span>
        <p className="ind-card__desc">{DESCRIPTIONS[c.id] || c.description || ""}</p>
        <p className="ind-card__figures">
          生値 {c.raw !== null ? c.raw.toLocaleString(undefined, { maximumFractionDigits: 2 }) : "—"}
          <span className="dot">•</span>
          重み {(c.weight * 100).toFixed(1)}%
        </p>
      </div>
    </article>
  );
}
