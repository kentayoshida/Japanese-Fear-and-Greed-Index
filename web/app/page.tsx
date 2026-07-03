"use client";

import { useEffect, useState } from "react";
import Gauge from "@/components/Gauge";
import ComparisonStrip from "@/components/ComparisonStrip";
import HistoryChart from "@/components/HistoryChart";
import IndicatorCard from "@/components/IndicatorCard";
import GuideView from "@/components/GuideView";
import { Latest, HistoryPoint, VariantInfo, VariantsManifest } from "@/lib/fgi";

// 静的 JSON は GitHub Actions の日次 cron が再生成・コミットする。
// クライアントから取得するため、再デプロイ後に最新値が反映される。
async function loadJson<T>(path: string): Promise<T> {
  const res = await fetch(path, { cache: "no-store" });
  if (!res.ok) throw new Error(`${path}: ${res.status}`);
  return (await res.json()) as T;
}

// レガシー（マニフェスト未生成）を表す擬似キー。latest.json/history.json を読む。
const LEGACY = "__legacy__";

type View = "dashboard" | "guide";

export default function Page() {
  const [view, setView] = useState<View>("dashboard");
  const [variants, setVariants] = useState<VariantInfo[]>([]);
  const [active, setActive] = useState<string | null>(null);
  const [latest, setLatest] = useState<Latest | null>(null);
  const [history, setHistory] = useState<HistoryPoint[]>([]);
  const [error, setError] = useState<string | null>(null);

  // ① 版マニフェストを読み、既定版をアクティブにする。無ければレガシー単一版。
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

  // ② アクティブ版のデータを読む（タブ切替で再取得）。読込中は前の値を保持。
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
      <div className="topnav__brand">日本版 Fear &amp; Greed Index</div>
      <div className="topnav__tabs" role="tablist">
        <button
          role="tab"
          aria-selected={view === "dashboard"}
          className={`topnav__tab${view === "dashboard" ? " is-active" : ""}`}
          onClick={() => setView("dashboard")}
        >
          ダッシュボード
        </button>
        <button
          role="tab"
          aria-selected={view === "guide"}
          className={`topnav__tab${view === "guide" ? " is-active" : ""}`}
          onClick={() => setView("guide")}
        >
          指標の解説
        </button>
      </div>
    </nav>
  );

  if (view === "guide") {
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

  return (
    <main className="page">
      {topnav}
      <header className="hero">
        <h1 className="hero__title">いま市場を動かしている感情は？</h1>
        <p className="hero__sub">
          日本株式市場の投資家心理を8つの指標から 0〜100 の単一スコアに合成しています。
        </p>

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

        <Gauge score={latest.score} />

        <div className="hero__meta">
          <span>基準日 {latest.as_of}</span>
          <span className="dot">•</span>
          <span>
            採用指標 {latest.coverage}/{latest.n_indicators}
          </span>
          {typeof latest.index_value === "number" && latest.index_label && (
            <>
              <span className="dot">•</span>
              <span>
                {latest.index_label}{" "}
                {latest.index_value.toLocaleString(undefined, { maximumFractionDigits: 2 })}
              </span>
            </>
          )}
          {latest.generated_at && (
            <>
              <span className="dot">•</span>
              <span>最終更新 {new Date(latest.generated_at).toLocaleString("ja-JP")}</span>
            </>
          )}
        </div>
      </header>

      <section className="section">
        <h2 className="section-title">時点比較</h2>
        <ComparisonStrip history={history} />
      </section>

      <section className="section">
        <HistoryChart history={history} indexLabel={latest.index_label} />
      </section>

      <section className="section">
        <h2 className="section-title">指標の内訳</h2>
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
          <p className="footer__gen">最終更新: {new Date(latest.generated_at).toLocaleString("ja-JP")}</p>
        )}
      </footer>
    </main>
  );
}
