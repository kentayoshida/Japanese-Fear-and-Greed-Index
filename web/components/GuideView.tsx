"use client";

// 解説（README）ビュー。マーケット初学者向けに、指数の考え方・各指標の意味・
// データソース・計算方法・正規化/合成の仕組みをやさしく説明する。

import { ZONES } from "@/lib/fgi";

type IndicatorDoc = {
  no: number;
  name: string;
  dimension: string;
  measures: string; // 何を測るか
  source: string; // データソース
  calc: string; // 計算方法
  high: string; // 高い/低いの意味
};

const INDICATORS: IndicatorDoc[] = [
  {
    no: 1,
    name: "株価指数 vs 125日移動平均の乖離率",
    dimension: "モメンタム",
    measures:
      "相場の「勢い」。株価指数が中期のトレンド（125日移動平均＝約半年の平均値）からどれだけ上/下に離れているか。",
    source: "TOPIX版=J-Quants の指数四本値、日経225版=日経公式の日次CSV。",
    calc: "乖離率(%) = (当日終値 − 125日移動平均) ÷ 125日移動平均 × 100。",
    high: "プラスに大きい＝平均より大きく上＝強気（Greed）。マイナス＝弱気（Fear）。",
  },
  {
    no: 2,
    name: "騰落レシオ（東証プライム・25日）",
    dimension: "ブレッドス（市場の幅）",
    measures:
      "上昇している銘柄がどれだけ「広く」多いか。一部の大型株だけでなく市場全体が上がっているかを見る。",
    source: "J-Quants の全銘柄終値から、日々の値上がり/値下がり銘柄数を集計。",
    calc:
      "直近25営業日の「値上がり銘柄数の合計 ÷ 値下がり銘柄数の合計 × 100」。120%超で過熱、70%割れで底値圏の目安。",
    high: "高い＝広く買われている＝強気。ただし過熱（買われ過ぎ）のサインにもなる。",
  },
  {
    no: 3,
    name: "新高値 − 新安値（東証全体・ネット）",
    dimension: "ブレッドス（市場の幅）",
    measures:
      "年初来（52週）高値をつけた銘柄と安値をつけた銘柄の差。相場の「地力」の強さ。",
    source: "J-Quants の全銘柄終値の52週（252営業日）高値・安値から判定。",
    calc: "新高値をつけた銘柄数 − 新安値をつけた銘柄数（ネット）。",
    high: "プラス＝新高値銘柄が多い＝強い相場（Greed）。マイナス＝崩れている（Fear）。",
  },
  {
    no: 4,
    name: "日経VI（ボラティリティ・インデックス）",
    dimension: "ボラティリティ",
    measures:
      "投資家が今後1か月の値動きの荒さ（不安）をどれだけ見込んでいるか。いわゆる「恐怖指数」の日本版。",
    source: "日経公式の日経VI 日次CSV。",
    calc: "日経225オプション価格から算出される予想変動率（％）。値そのものを使用。",
    high: "高い＝不安が大きい＝Fear。そのため本指標は反転して合成（高VI→低スコア）。",
  },
  {
    no: 5,
    name: "日経225オプション Put/Call レシオ",
    dimension: "ヘッジ / ポジショニング",
    measures:
      "下落に備える「保険」（プット）がどれだけ買われているか。投資家の警戒度。",
    source: "J-Quants の日経225オプション四本値（出来高）。",
    calc: "その日のプット出来高 ÷ コール出来高。",
    high: "高い＝下落ヘッジ需要が強い＝Fear。反転して合成。",
  },
  {
    no: 7,
    name: "空売り比率（東証）",
    dimension: "ヘッジ / ポジショニング",
    measures: "売買のうち「空売り（下落に賭ける売り）」が占める割合。弱気姿勢の強さ。",
    source: "J-Quants の業種別空売り比率を市場全体に合算。",
    calc: "(規制あり空売り + 規制なし空売り) ÷ (実売り + 空売り合計) × 100。",
    high: "高い＝弱気/ヘッジが強い＝Fear。反転して合成。",
  },
  {
    no: 6,
    name: "信用評価損益率（買い方）",
    dimension: "レバレッジ / 個人心理",
    measures:
      "信用取引で株を買っている個人投資家が、平均でどれだけ含み益/含み損かの割合。個人の楽観・悲観の温度計。",
    source:
      "松井証券「投資指標（店内）」の最新値（正）＋ J-Quants の週次信用買い残から推計した過去分（三層構成・下記）。",
    calc:
      "評価損益率(%)。おおむね 0%近辺で楽観、−20%以下で強い悲観。アンカー（-30→0, -20→20, -10→50, 0→100）で0-100化。",
    high: "高い（含み損が浅い/含み益）＝個人が強気。低い（含み損が深い）＝個人の恐怖。",
  },
  {
    no: 8,
    name: "セーフヘイブン需要（株式 − 債券 20日リターン差）",
    dimension: "安全資産選好",
    measures:
      "お金が「リスク資産（株）」と「安全資産（債券）」のどちらに向かっているか。",
    source: "版の株価指数 と 国債ETF(2510) の調整後終値。",
    calc: "株式の20日リターン − 債券の20日リターン（％）。",
    high: "プラス＝株が債券に勝っている＝リスク選好（Greed）。マイナス＝安全資産へ逃避（Fear）。",
  },
];

export default function GuideView() {
  return (
    <div className="guide">
      <header className="guide__hero">
        <div className="hero__eyebrow">解説</div>
        <h1 className="guide__title">Fear &amp; Greed Index の読み方</h1>
        <p className="guide__lead">
          相場は最終的に「恐怖（Fear）」と「強欲（Greed）」という2つの感情で動く、という考え方があります。
          本指数は、日本株式市場のさまざまなデータを 0〜100 の単一スコアにまとめ、
          いま市場心理がどちらに傾いているかを一目で分かるようにしたものです。
        </p>
      </header>

      <section className="guide__section">
        <h2 className="guide__h2">スコアの読み方</h2>
        <p className="guide__p">
          スコアは 0（極度の恐怖）〜 100（極度の貪欲）。一般に、
          <strong>極端な恐怖は「売られ過ぎ」の目安</strong>、
          <strong>極端な貪欲は「買われ過ぎ」の目安</strong>として、逆張りの参考に使われます
          （＝みんなが怖がっている時こそ好機、という逆張り思想）。
        </p>
        <div className="guide__zones">
          {ZONES.map((z) => (
            <div className="guide__zone" key={z.key}>
              <span className="guide__zone-swatch" style={{ background: z.color }} />
              <span className="guide__zone-range">
                {z.min}–{z.max}
              </span>
              <span className="guide__zone-label">{z.labelJa}</span>
            </div>
          ))}
        </div>
      </section>

      <section className="guide__section">
        <h2 className="guide__h2">8つの指標</h2>
        <p className="guide__p">
          スコアは 6つの「心理次元」（モメンタム／市場の幅／ボラティリティ／ヘッジ・ポジショニング／
          レバレッジ・個人心理／安全資産選好）に均等な重みを置き、各次元の指標を合成しています。
          一部の指標が取得できない日は、その指標を除いて残りで重みを再配分します
          （欠損を50＝中立で埋めません）。
        </p>
        <div className="guide__cards">
          {INDICATORS.map((d) => (
            <article className="guide-card" key={d.no}>
              <div className="guide-card__head">
                <span className="guide-card__no">#{d.no}</span>
                <div>
                  <h3 className="guide-card__name">{d.name}</h3>
                  <span className="guide-card__dim">{d.dimension}</span>
                </div>
              </div>
              <dl className="guide-card__dl">
                <dt>何を測る？</dt>
                <dd>{d.measures}</dd>
                <dt>データソース</dt>
                <dd>{d.source}</dd>
                <dt>計算方法</dt>
                <dd>{d.calc}</dd>
                <dt>高い/低いの意味</dt>
                <dd>{d.high}</dd>
              </dl>
            </article>
          ))}
        </div>
      </section>

      <section className="guide__section">
        <h2 className="guide__h2">スコア化（正規化）の考え方</h2>
        <ul className="guide__ul">
          <li>
            <strong>パーセンタイル方式</strong>：直近約1年（252営業日）の中で、今日の値が何％の位置に
            あるかで 0〜100 に変換。分布の形を仮定せず外れ値に強い方式です。
          </li>
          <li>
            <strong>アンカー方式</strong>：騰落レシオや信用評価損益率のように「経験的な目安（しきい値）」が
            ある指標は、固定の基準点（例：信用評価損益率 −30%→0点、0%→100点）で変換します。
          </li>
          <li>
            <strong>反転</strong>：日経VI・P/Cレシオ・空売り比率は「高い＝恐怖」なので、スコア化後に
            100から引いて向きをそろえます。
          </li>
          <li>
            <strong>point-in-time（先読み防止）</strong>：過去の各日について、その日までに実際に入手できた
            データだけで計算します。未来の情報は使いません。
          </li>
        </ul>
      </section>

      <section className="guide__section">
        <h2 className="guide__h2">TOPIX版 と 日経225版</h2>
        <p className="guide__p">
          相場の「勢い（#1）」と「安全資産選好（#8）」に使う株価指数だけを、TOPIX または 日経平均に
          差し替えた2つの版を用意しています。値動きの幅が広い銘柄の影響を受けやすい日経225と、
          市場全体を時価総額加重で表すTOPIXでは、同じ日でもスコアが異なることがあります。
          その他の指標（市場の幅・ボラティリティ・ヘッジ・個人心理）は両版で共通です。
        </p>
      </section>

      <section className="guide__section">
        <h2 className="guide__h2">#6 信用評価損益率の三層構成</h2>
        <p className="guide__p">
          #6 は個人心理をよく映す指標ですが、公開値は「最新日の1点」しか手に入りません。そこで過去分を
          次の三層で補います。
        </p>
        <ol className="guide__ol">
          <li>
            <strong>tier-1（正）</strong>：松井証券のページから最新営業日の実測値を取得。
          </li>
          <li>
            <strong>tier-2（近似）</strong>：市場全体の週次「信用買い残高」と株価指数から、平均建値を
            推計して日々の含み損益率を近似（在庫平均コスト法によるマーク・トゥ・マーケット）。
          </li>
          <li>
            <strong>tier-3（較正）</strong>：実測値が得られた日で近似値のズレを補正します。実測点が
            貯まるほど精度が上がります。
          </li>
        </ol>
      </section>

      <p className="guide__disclaimer">
        ⚠ 本指標は情報提供・学習目的の自作指標であり、投資助言ではありません。売買の判断はご自身の責任で
        行ってください。
      </p>
    </div>
  );
}
