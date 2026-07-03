"use client";

import { useEffect, useState } from "react";
import Gauge from "@/components/Gauge";
import ComparisonStrip from "@/components/ComparisonStrip";
import HistoryChart from "@/components/HistoryChart";
import IndicatorCard from "@/components/IndicatorCard";
import GuideView from "@/components/GuideView";
import { Latest, HistoryPoint, VariantInfo, VariantsManifest } from "@/lib/fgi";

// 静的 JSON は GitHub Actions の日次 cron が再生成・コミットする。
async function loadJson<T>(path: string): Promise<T> {
  const res = await fetch(path, { cache: "no-store" });
  if (!res.ok) throw new Error(`${path}: ${res.status}`);
  return (await res.json()) as T;
}

// レガシー（マニフェスト未生成）を表す擬似キー。latest.json/history.json を読む。
const LEGACY = "__legacy__";

type Graph = "overview" | "timeline";

export default function Page() {
  const [guide, setGuide] = useState(false);
  const [graph, setGraph] = useState<Graph>("overview");
  const [variants, setVariants] = useState<VariantInfo[]>([]);
  const [active, setActive] = useState<string | null>(null);
  const [latest, setLatest] = useState<Latest | null>(null);
  const [history, setHistory] = useState<HistoryPoint[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadJson<VariantsManifest>("/data/variants.json")
      .then((m) => {
        const vs = m.variants ?? [];
        if (vs.length === 0) throw new Error("empty manifest");
        setVariants(vs);
        setActive((vs.find((v) => v.default) ?? vs[0]).key);
      })
      .catch(() => {
        setVariants([]);
        setActive(LEGACY);
      });
  }, []);

  useEffect(() => {
    if (!active) return;
    const suffix = active === LEGACY ? "" : `.${active}`;
    Promise.all([
      loadJson<Latest>(`/data/latest${suffix}.json`),
      loadJson<HistoryPoint[]>(`/data/history${suffix}.json`),
    ])
      .then(([l, h]) => {
        setLatest(l);
        setHistory(h);
        setError(null);
      })
      .catch((e) => setError(String(e)));
  }, [active]);

  const topnav = (
    <nav className="topnav" aria-label="ビュー切り替え">
      <div className="topnav__brand">恐怖と強欲指数</div>
      <div className="topnav__tabs" role="tablist">
        <button
          role="tab"
          aria-selected={!guide}
          className={`topnav__tab${!guide ? " is-active" : ""}`}
          onClick={() => setGuide(false)}
        >
          ダッシュボード
        </button>
        <button
          role="tab"
          aria-selected={guide}
          className={`topnav__tab${guide ? " is-active" : ""}`}
          onClick={() => setGuide(true)}
        >
          指標の解説
        </button>
      </div>
    </nav>
  );

  if (guide) {
    return (
      <main className="page">
        {topnav}
        <GuideView />
      </main>
    );
  }

  if (error) {
    return (
      <main className="page">
        {topnav}
        <div className="empty-state">データを読み込めませんでした。<br />{error}</div>
      </main>
    );
  }

  if (!latest) {
    return (
      <main className="page">
        {topnav}
        <div className="empty-state">読み込み中…</div>
      </main>
    );
  }

  const graphToggle = (
    <div className="graph-toggle" role="tablist" aria-label="グラフ切り替え">
      <button
        role="tab"
        aria-selected={graph === "overview"}
        className={`graph-toggle__btn${graph === "overview" ? " is-active" : ""}`}
        onClick={() => setGraph("overview")}
      >
        概要
      </button>
      <button
        role="tab"
        aria-selected={graph === "timeline"}
        className={`graph-toggle__btn${graph === "timeline" ? " is-active" : ""}`}
        onClick={() => setGraph("timeline")}
      >
        推移
      </button>
    </div>
  );

  return (
    <main className="page">
      {topnav}
      <header className="hero">
        <div className="hero__eyebrow">恐怖と強欲指数（日本株版）</div>
        <h1 className="hero__title">いま市場を動かしている感情は？</h1>
        {variants.length > 1 && (
          <div className="variant-tabs" role="tablist" aria-label="指数版の切り替え">
            {variants.map((v) => (
              <button
                key={v.key}
                role="tab"
                aria-selected={active === v.key}
                className={`variant-tab${active === v.key ? " is-active" : ""}`}
                onClick={() => setActive(v.key)}
              >
                {v.label_ja}版
              </button>
            ))}
          </div>
        )}
        {latest.sample && (
          <div className="notice notice--sample">
            ⚠ これはサンプル（合成データ）です。実データソース（J-Quants 等）を結線すると本番値に切り替わります。
          </div>
        )}
      </header>

      {/* グラフパネル：右上トグルで ゲージ(概要) ⇄ ラインチャート(推移) を切替。
          下部の構成指標カードは常に表示（切替の影響を受けない）。 */}
      <section className="graphpanel">
        <div className="graphpanel__head">{graphToggle}</div>

        {graph === "overview" ? (
          <div className="overview">
            <div className="overview__gauge">
              <Gauge score={latest.score} />
              <div className="hero__meta">
                <span>基準日 {latest.as_of}</span>
                <span className="dot">•</span>
                <span>採用指標 {latest.coverage}/{latest.n_indicators}</span>
                {typeof latest.index_value === "number" && latest.index_label && (
                  <>
                    <span className="dot">•</span>
                    <span>
                      {latest.index_label}{" "}
                      {latest.index_value.toLocaleString(undefined, { maximumFractionDigits: 2 })}
                    </span>
                  </>
                )}
              </div>
            </div>
            <div className="overview__compare">
              <ComparisonStrip history={history} />
            </div>
          </div>
        ) : (
          <HistoryChart history={history} indexLabel={latest.index_label} />
        )}
      </section>

      {/* 構成指標（常時表示） */}
      <section className="section">
        <h2 className="section-title">{latest.n_indicators}個の構成指標</h2>
        <div className="indicator-grid">
          {latest.components.map((c) => (
            <IndicatorCard key={c.id} c={c} generatedAt={latest.generated_at} />
          ))}
        </div>
      </section>

      <footer className="footer">
        <p className="disclaimer">
          {latest.disclaimer ??
            "本指標は情報提供目的の自作指標であり、投資助言ではありません。"}
        </p>
        {latest.generated_at && (
          <p className="footer__gen">
            最終更新: {new Date(latest.generated_at).toLocaleString("ja-JP")}
          </p>
        )}
      </footer>
    </main>
  );
}
