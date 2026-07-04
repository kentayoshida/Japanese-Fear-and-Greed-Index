"use client";

// 指標カード（本家CNN型）。2カラム：
//  左＝eyebrow(カテゴリ)＋指標名＋生値ラインチャート(右軸)＋基準日/取得
//  右＝状態バッジ（現在の判定）＋説明文（2〜3文）

import {
  CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { Component, colorForScore, labelForScore } from "@/lib/fgi";
import { useLang, t, DIM, IND_NAME, IND_SUB, IND_DESC, pick } from "@/lib/i18n";

function formatFetched(iso: string | undefined, lang: string): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleString(lang === "en" ? "en-US" : "ja-JP", {
    year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit",
  });
}

function monthTick(d: string): string {
  return d.length >= 7 ? d.slice(0, 7).replace("-", "/") : d;
}

function makeRawTooltip() {
  return function RawTooltip({ active, payload, label }: any) {
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
  };
}

function RawChart({ series, accumLabel }: { series: { d: string; v: number | null }[]; accumLabel: string }) {
  const valid = series.filter((p) => typeof p.v === "number");
  if (valid.length < 2) {
    return <div className="rawchart rawchart--empty">{accumLabel}</div>;
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
          <Tooltip content={makeRawTooltip()} />
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
  const { lang } = useLang();
  const fetched = formatFetched(generatedAt, lang);
  const series = c.series ?? [];
  const badgeColor = c.score !== null ? colorForScore(c.score) : "#9aa0a6";
  const badgeText = c.score !== null ? labelForScore(c.score, lang) : t(lang, "chartAccum");
  const title = lang === "en" ? (IND_NAME[c.id] ?? c.label) : c.label;

  return (
    <article className={`ind-card ${c.stale ? "is-stale" : ""}`}>
      <div className="ind-card__main">
        <div className="fg-eyebrow">{pick(DIM[c.dimension], lang, c.dimension)}</div>
        <h3 className="ind-card__title">{title}</h3>
        <div className="ind-card__sub">{pick(IND_SUB[c.id], lang)}</div>
        <RawChart series={series} accumLabel={t(lang, "chartAccum")} />
        <div className="ind-card__updated">
          {c.data_date && <span>{t(lang, "cardAsOf")} {c.data_date}</span>}
          {c.data_date && fetched && <span className="dot">•</span>}
          {fetched && <span>{t(lang, "cardFetched")} {fetched}</span>}
        </div>
      </div>

      <div className="ind-card__side">
        <span className="ind-badge" style={{ color: badgeColor, borderColor: badgeColor }}>
          {badgeText}
        </span>
        <p className="ind-card__desc">{pick(IND_DESC[c.id], lang, c.description || "")}</p>
        <p className="ind-card__figures">
          {t(lang, "cardValue")} {c.raw !== null ? c.raw.toLocaleString(undefined, { maximumFractionDigits: 2 }) : "—"}
          <span className="dot">•</span>
          {t(lang, "cardWeight")} {(c.weight * 100).toFixed(1)}%
        </p>
      </div>
    </article>
  );
}
