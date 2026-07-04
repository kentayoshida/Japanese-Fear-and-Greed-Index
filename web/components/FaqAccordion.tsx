"use client";

// FAQ アコーディオン（日本語 / English）。

import { useLang, t } from "@/lib/i18n";

const FAQ: { q: { ja: string; en: string }; a: { ja: string; en: string } }[] = [
  {
    q: { ja: "「恐怖と強欲指数」とは何ですか？", en: "What is the Fear & Greed Index?" },
    a: {
      ja: "日本株式市場の投資家心理を、複数の独立した市場指標から 0〜100 の単一スコアに合成した自作指標です。相場は最終的に「恐怖」と「強欲」で動くという考えに基づき、過度な恐怖は株価を押し下げ、過度な強欲はその逆に働く、というロジックを可視化します。",
      en: "It is an independent index that condenses investor sentiment in the Japanese stock market into a single 0–100 score built from several independent market indicators. Based on the idea that markets are ultimately driven by fear and greed, it visualizes the logic that excessive fear tends to push prices down while excessive greed does the opposite.",
    },
  },
  {
    q: { ja: "どのように計算していますか？", en: "How is it calculated?" },
    a: {
      ja: "8つの指標を6つの心理次元（モメンタム／市場の幅／ボラティリティ／ヘッジ・ポジショニング／レバレッジ・個人心理／安全資産選好）に束ね、各次元へ均等に重みを置いて合成します。各指標は直近約1年の分布での位置（パーセンタイル）や、経験的なしきい値（アンカー）で 0〜100 に正規化します。取得できない指標はその日の合成から除外し、残りの次元で重みを配分し直します（欠損を中立の50で埋めません）。",
      en: "Eight indicators are grouped into six psychological dimensions (momentum, breadth, volatility, hedging & positioning, leverage & retail sentiment, and safe-haven demand), and the dimensions are weighted equally. Each indicator is normalized to 0–100 by its percentile within roughly the past year, or by empirical thresholds (anchors). Any indicator that cannot be fetched is dropped for that day and the weights are re-normalized over the remaining dimensions (missing values are never filled with a neutral 50).",
    },
  },
  {
    q: { ja: "どのくらいの頻度で更新されますか？", en: "How often is it updated?" },
    a: {
      ja: "GitHub Actions の日次ジョブが、日本市場の引け後・各データの発表ラグを見て 1 日 1 回スコアを再生成します。過去の各日は「その日までに実際に入手できたデータ」だけで計算しており、未来の情報は使いません（先読み防止）。",
      en: "A daily GitHub Actions job regenerates the score once per day after the Japanese market close, accounting for each data source's publication lag. Every past day is computed using only the data that was actually available at that point in time — no future information is used (point-in-time discipline).",
    },
  },
  {
    q: { ja: "どう使えばよいですか？", en: "How should I use it?" },
    a: {
      ja: "市場の温度感を測る補助ツールです。多くの投資家は感情に流されやすく、極端な恐怖は「売られ過ぎ」、極端な強欲は「買われ過ぎ」の目安として、逆張りの参考に使われます。ファンダメンタルズや他の分析と併用してください。本指標は情報提供目的であり、投資助言ではありません。",
      en: "It is a supplementary tool for gauging the mood of the market. Because many investors act emotionally, extreme fear is often used as a rough 'oversold' signal and extreme greed as an 'overbought' one, as a contrarian reference. Use it alongside fundamentals and other analysis. This index is for information only and is not investment advice.",
    },
  },
  {
    q: { ja: "TOPIX版と日経225版の違いは？", en: "What is the difference between the TOPIX and Nikkei 225 versions?" },
    a: {
      ja: "勢い（#1 モメンタム）と安全資産選好（#8）に使う株価指数だけを、TOPIX または 日経平均に差し替えた2つの版です。指数の値動きの寄与が異なるため、同じ日でもスコアが違うことがあります。その他の指標（市場の幅・ボラティリティ・ヘッジ・個人心理）は両版で共通です。",
      en: "They are two versions that differ only in the stock index used for momentum (#1) and safe-haven demand (#8) — either TOPIX or the Nikkei 225. Because each index contributes differently, the score can differ on the same day. All other indicators (breadth, volatility, hedging, retail sentiment) are shared by both versions.",
    },
  },
];

export default function FaqAccordion() {
  const { lang } = useLang();
  return (
    <section className="section faq">
      <h2 className="section-title">{t(lang, "faqTitle")}</h2>
      <div className="faq__list">
        {FAQ.map((item, i) => (
          <details className="faq__item" key={i}>
            <summary className="faq__q">
              <span>{item.q[lang]}</span>
              <span className="faq__chev" aria-hidden="true" />
            </summary>
            <p className="faq__a">{item.a[lang]}</p>
          </details>
        ))}
      </div>
    </section>
  );
}
