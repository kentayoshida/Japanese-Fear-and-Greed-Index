"use client";

import { useEffect, useState } from "react";
import Gauge from "@/components/Gauge";
import ComparisonStrip from "@/components/ComparisonStrip";
import HistoryChart from "@/components/HistoryChart";
import IndicatorCard from "@/components/IndicatorCard";
import FaqAccordion from "@/components/FaqAccordion";
import GuideView from "@/components/GuideView";
import { Latest, HistoryPoint, VariantInfo, VariantsManifest } from "@/lib/fgi";
import { Lang, LangContext, t, variantTab, indicatorsHeading, variantLabel } from "@/lib/i18n";

async function loadJson<T>(path: string): Promise<T> {
  const res = await fetch(path, { cache: "no-store" });
  if (!res.ok) throw new Error(`${path}: ${res.status}`);
  return (await res.json()) as T;
}

const LEGACY = "__legacy__";
type Graph = "overview" | "timeline";

export default function Page() {
  const [lang, setLang] = useState<Lang>("ja");
  const [guide, setGuide] = useState(false);
  const [graph, setGraph] = useState<Graph>("overview");
  const [variants, setVariants] = useState<VariantInfo[]>([]);
  const [active, setActive] = useState<string | null>(null);
  const [latest, setLatest] = useState<Latest | null>(null);
  const [history, setHistory] = useState<HistoryPoint[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const saved = typeof window !== "undefined" ? window.localStorage.getItem("fgi-lang") : null;
    if (saved === "en" || saved === "ja") setLang(saved);
  }, []);
  const changeLang = (l: Lang) => {
    setLang(l);
    try {
      window.localStorage.setItem("fgi-lang", l);
    } catch {}
  };

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
    <nav className="topnav" aria-label="navigation">
      <div className="topnav__brand">{t(lang, "brand")}</div>
      <div className="topnav__right">
        <div className="topnav__tabs" role="tablist">
          <button
            role="tab"
            aria-selected={!guide}
            className={`topnav__tab${!guide ? " is-active" : ""}`}
            onClick={() => setGuide(false)}
          >
            {t(lang, "navDashboard")}
          </button>
          <button
            role="tab"
            aria-selected={guide}
            className={`topnav__tab${guide ? " is-active" : ""}`}
            onClick={() => setGuide(true)}
          >
            {t(lang, "navGuide")}
          </button>
        </div>
        <div className="lang-switch" role="group" aria-label="Language">
          <button className={lang === "ja" ? "is-active" : ""} onClick={() => changeLang("ja")}>
            日本語
          </button>
          <button className={lang === "en" ? "is-active" : ""} onClick={() => changeLang("en")}>
            EN
          </button>
        </div>
      </div>
    </nav>
  );

  let body: React.ReactNode;
  if (guide) {
    body = (
      <main className="page">
        {topnav}
        <GuideView />
      </main>
    );
  } else if (error) {
    body = (
      <main className="page">
        {topnav}
        <div className="empty-state">{t(lang, "loadError")}<br />{error}</div>
      </main>
    );
  } else if (!latest) {
    body = (
      <main className="page">
        {topnav}
        <div className="empty-state">{t(lang, "loading")}</div>
      </main>
    );
  } else {
    const graphToggle = (
      <div className="graph-toggle" role="tablist" aria-label="graph view">
        <button
          role="tab"
          aria-selected={graph === "overview"}
          className={`graph-toggle__btn${graph === "overview" ? " is-active" : ""}`}
          onClick={() => setGraph("overview")}
        >
          {t(lang, "overview")}
        </button>
        <button
          role="tab"
          aria-selected={graph === "timeline"}
          className={`graph-toggle__btn${graph === "timeline" ? " is-active" : ""}`}
          onClick={() => setGraph("timeline")}
        >
          {t(lang, "timeline")}
        </button>
      </div>
    );

    body = (
      <main className="page">
        {topnav}
        <header className="hero">
          <div className="hero__eyebrow">{t(lang, "heroEyebrow")}</div>
          <h1 className="hero__title">{t(lang, "heroTitle")}</h1>
          {variants.length > 1 && (
            <div className="variant-tabs" role="tablist" aria-label="index variant">
              {variants.map((v) => (
                <button
                  key={v.key}
                  role="tab"
                  aria-selected={active === v.key}
                  className={`variant-tab${active === v.key ? " is-active" : ""}`}
                  onClick={() => setActive(v.key)}
                >
                  {variantTab(v.key, v.label_ja, lang)}
                </button>
              ))}
            </div>
          )}
          {latest.sample && <div className="notice notice--sample">{t(lang, "sample")}</div>}
        </header>

        <section className="graphpanel">
          <div className="graphpanel__head">{graphToggle}</div>

          {graph === "overview" ? (
            <div className="overview">
              <div className="overview__gauge">
                <Gauge score={latest.score} />
                <div className="hero__meta">
                  <span>{t(lang, "asOf")} {latest.as_of}</span>
                  <span className="dot">•</span>
                  <span>{t(lang, "coverage")} {latest.coverage}/{latest.n_indicators}</span>
                  {typeof latest.index_value === "number" && (
                    <>
                      <span className="dot">•</span>
                      <span>
                        {variantLabel(active ?? "", latest.index_label ?? "", lang)}{" "}
                        {latest.index_value.toLocaleString(undefined, { maximumFractionDigits: 2 })}
                      </span>
                    </>
                  )}
                  {latest.generated_at && (
                    <>
                      <span className="dot">•</span>
                      <span>{t(lang, "updated")} {new Date(latest.generated_at).toLocaleString(lang === "en" ? "en-US" : "ja-JP")}</span>
                    </>
                  )}
                </div>
              </div>
              <div className="overview__compare">
                <ComparisonStrip history={history} />
              </div>
            </div>
          ) : (
            <HistoryChart history={history} indexLabel={variantLabel(active ?? "", latest.index_label ?? "", lang)} />
          )}
        </section>

        <section className="section">
          <h2 className="section-title">{indicatorsHeading(latest.n_indicators, lang)}</h2>
          <div className="indicator-grid">
            {latest.components.map((c) => (
              <IndicatorCard key={c.id} c={c} generatedAt={latest.generated_at} />
            ))}
          </div>
        </section>

        <FaqAccordion />

        <footer className="footer">
          <p className="disclaimer">{t(lang, "disclaimer")}</p>
          {latest.generated_at && (
            <p className="footer__gen">
              {t(lang, "footerUpdated")}: {new Date(latest.generated_at).toLocaleString(lang === "en" ? "en-US" : "ja-JP")}
            </p>
          )}
        </footer>
      </main>
    );
  }

  return <LangContext.Provider value={{ lang, setLang: changeLang }}>{body}</LangContext.Provider>;
}
