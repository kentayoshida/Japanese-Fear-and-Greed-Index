#!/usr/bin/env python3
"""X（Twitter）投稿用の Fear & Greed ゲージ画像（PNG）を生成する。

`web/public/data/latest.<variant>.json` の値から自己完結 HTML を組み立て、
Playwright(chromium) で 1200×675 の PNG にスクリーンショットする。X のタイムラインは
16:9 で表示されるため、この比率にしておくと切れずに全体が出る。

ゲージの幾何・配色は Web 版 `web/components/Gauge.tsx` / `web/lib/fgi.ts` /
`web/app/design-tokens.css` と一致させ、サイトと同じ見た目にする（別実装で数値が
ズレないよう、バンド境界・色・角度計算をそのまま移植）。

CLI:
  python scripts/x_card.py                 # 既定版(nikkei225)の latest から card.png
  python scripts/x_card.py --variant topix --out /tmp/topix.png
"""

from __future__ import annotations

import argparse
import json
import math
import tempfile
from pathlib import Path

ENGINE_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ENGINE_ROOT.parent / "web" / "public" / "data"

# --- ゲージ幾何（Gauge.tsx と同一） ---
CX, CY = 200, 196
R_OUT, R_IN = 172, 108
R_MID = (R_OUT + R_IN) / 2
NEEDLE_LEN = R_IN - 4
HUB = 46

# --- 5ゾーン（web/lib/fgi.ts ZONES と同一。色は design-tokens.css と一致） ---
ZONES = [
    {"min": 0, "max": 25, "color": "#c0392b", "ja": "極度の恐怖", "en": "Extreme Fear"},
    {"min": 25, "max": 45, "color": "#e67e22", "ja": "恐怖", "en": "Fear"},
    {"min": 45, "max": 55, "color": "#e6b800", "ja": "中立", "en": "Neutral"},
    {"min": 55, "max": 75, "color": "#7cb342", "ja": "貪欲", "en": "Greed"},
    {"min": 75, "max": 100, "color": "#1a9850", "ja": "極度の貪欲", "en": "Extreme Greed"},
]
ZONE_BG = "#eceef1"  # 非アクティブゾーンの地色


def zone_for_score(score: float) -> dict:
    for z in ZONES:
        if z["min"] <= score < z["max"]:
            return z
    return ZONES[-1]


def _tint(hex_color: str, pct: int) -> str:
    """color-mix(in srgb, color pct%, white) 相当。バンド色を白で薄めた地色を作る。"""
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    f = pct / 100.0
    r = round(r * f + 255 * (1 - f))
    g = round(g * f + 255 * (1 - f))
    b = round(b * f + 255 * (1 - f))
    return f"#{r:02x}{g:02x}{b:02x}"


def _value_to_angle(v: float) -> float:
    c = max(0.0, min(100.0, v))
    return 180 - (c / 100) * 180


def _polar(r: float, deg: float) -> tuple[float, float]:
    a = deg * math.pi / 180
    return CX + r * math.cos(a), CY - r * math.sin(a)


def _ring_sector_path(s: float, e: float) -> str:
    a0, a1 = _value_to_angle(s), _value_to_angle(e)
    oS, oE = _polar(R_OUT, a0), _polar(R_OUT, a1)
    iE, iS = _polar(R_IN, a1), _polar(R_IN, a0)
    return (
        f"M {oS[0]:.2f} {oS[1]:.2f} "
        f"A {R_OUT} {R_OUT} 0 0 1 {oE[0]:.2f} {oE[1]:.2f} "
        f"L {iE[0]:.2f} {iE[1]:.2f} "
        f"A {R_IN} {R_IN} 0 0 0 {iS[0]:.2f} {iS[1]:.2f} Z"
    )


def _gauge_svg(score: float | None) -> str:
    has = score is not None and not (isinstance(score, float) and math.isnan(score))
    value = float(score) if has else 50.0
    active = zone_for_score(value)
    needle_rot = value * 1.8 - 90

    parts: list[str] = ['<svg viewBox="-6 0 412 236" xmlns="http://www.w3.org/2000/svg">']

    # 5ゾーン（既定グレー、アクティブのみ淡色地＋色枠）
    for z in ZONES:
        is_active = has and z is active
        fill = _tint(z["color"], 22) if is_active else ZONE_BG
        stroke = z["color"] if is_active else "#ffffff"
        sw = 2 if is_active else 3
        parts.append(
            f'<path d="{_ring_sector_path(z["min"], z["max"])}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>'
        )

    # ゾーン名（弧に沿って回転）
    for z in ZONES:
        mid = (z["min"] + z["max"]) / 2
        a = _value_to_angle(mid)
        px, py = _polar(R_MID, a)
        rot = 90 - a
        is_active = has and z is active
        fs = 9.5 if (z["min"] == 0 or z["max"] == 100) else 11
        fill = z["color"] if is_active else "#8a929b"
        parts.append(
            f'<text x="{px:.2f}" y="{py:.2f}" font-size="{fs}" font-weight="700" '
            f'letter-spacing="0.02em" fill="{fill}" text-anchor="middle" '
            f'dominant-baseline="middle" '
            f'transform="rotate({rot:.2f} {px:.2f} {py:.2f})">{z["ja"]}</text>'
        )

    # 内側の細かい目盛り点（5刻み）
    for i in range(21):
        t = i * 5
        px, py = _polar(R_IN - 8, _value_to_angle(t))
        parts.append(f'<circle cx="{px:.2f}" cy="{py:.2f}" r="1.1" fill="#c7ccd1"/>')

    # 数値目盛り 0/25/50/75/100
    for t in (0, 25, 50, 75, 100):
        px, py = _polar(R_IN - 20, _value_to_angle(t))
        parts.append(
            f'<text x="{px:.2f}" y="{py:.2f}" font-size="12" fill="#5a6570" '
            f'text-anchor="middle" dominant-baseline="middle">{t}</text>'
        )

    # 針
    if has:
        parts.append(
            f'<g transform="rotate({needle_rot:.2f} {CX} {CY})">'
            f'<polygon points="{CX - 9},{CY} {CX},{CY - NEEDLE_LEN} {CX + 9},{CY}" '
            f'fill="#0d0d0d"/></g>'
        )

    # 下部中央の白円＋スコア
    parts.append(
        f'<circle cx="{CX}" cy="{CY}" r="{HUB}" fill="#ffffff" '
        f'stroke="#e0e0e0" stroke-width="1.5"/>'
    )
    score_txt = str(round(value)) if has else "—"
    parts.append(
        f'<text x="{CX}" y="{CY - 6}" font-size="46" font-weight="700" fill="#0d0d0d" '
        f'text-anchor="middle" dominant-baseline="middle" '
        f'font-family="Inter, sans-serif" style="font-variant-numeric:tabular-nums">{score_txt}</text>'
    )
    parts.append("</svg>")
    return "".join(parts)


def _short_date(as_of: str) -> str:
    """'2026-07-17' → '7/17'。解釈できなければそのまま返す。"""
    try:
        _, m, d = as_of.split("-")
        return f"{int(m)}/{int(d)}"
    except Exception:  # noqa: BLE001
        return as_of


def build_html(latest: dict, site_domain: str = "") -> str:
    """latest.json の1版ぶんから、スクショ用の自己完結 HTML を作る。"""
    score = latest.get("score")
    has = score is not None
    active = zone_for_score(float(score)) if has else None
    band_ja = latest.get("band_label_ja") or (active["ja"] if active else "—")
    band_en = latest.get("band") or (active["en"] if active else "")
    band_color = active["color"] if active else "#5a6570"
    variant_label = latest.get("variant_label") or latest.get("index_label") or "日経225"
    as_of = latest.get("as_of", "")
    index_label = latest.get("index_label", variant_label)
    index_value = latest.get("index_value")
    index_line = ""
    if index_value is not None:
        index_line = f'{index_label} <b>{index_value:,.2f}</b>'

    return f"""<!DOCTYPE html>
<html lang="ja"><head><meta charset="utf-8"><style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  html,body {{ width:1200px; height:675px; }}
  body {{
    font-family:"Inter","Noto Sans JP","Hiragino Kaku Gothic ProN",sans-serif;
    background:#ffffff; color:#0d0d0d; -webkit-font-smoothing:antialiased;
  }}
  .card {{
    width:1200px; height:675px; padding:56px 64px;
    display:flex; flex-direction:column;
    border-top:6px solid {band_color};
  }}
  .eyebrow {{ font-size:20px; font-weight:600; letter-spacing:0.08em;
    text-transform:uppercase; color:#5a6570; }}
  .title {{ font-size:44px; font-weight:800; margin-top:6px; letter-spacing:-0.01em; }}
  .subtitle {{ font-size:22px; color:#5a6570; margin-top:8px; }}
  .main {{ flex:1; display:flex; align-items:center; justify-content:space-between; gap:24px; }}
  .gauge {{ width:660px; }}
  .gauge svg {{ width:100%; height:auto; display:block; }}
  .readout {{ flex:1; text-align:right; }}
  .band {{ font-size:72px; font-weight:800; line-height:1.05; color:{band_color}; }}
  .band-en {{ font-size:28px; font-weight:600; color:{band_color}; opacity:0.85; margin-top:4px; }}
  .index {{ font-size:30px; color:#0d0d0d; margin-top:28px; }}
  .index b {{ font-variant-numeric:tabular-nums; }}
  .footer {{ display:flex; justify-content:space-between; align-items:flex-end;
    border-top:1px solid #e0e0e0; padding-top:18px; }}
  .footer .site {{ font-size:22px; font-weight:700; color:#0d0d0d; }}
  .footer .disc {{ font-size:16px; color:#8a929b; max-width:640px; text-align:right; }}
</style></head><body>
  <div class="card">
    <div>
      <div class="eyebrow">Japan Fear &amp; Greed Index</div>
      <div class="title">日本版 Fear &amp; Greed 指数</div>
      <div class="subtitle">{variant_label} ・ {as_of} 時点</div>
    </div>
    <div class="main">
      <div class="gauge">{_gauge_svg(score)}</div>
      <div class="readout">
        <div class="band">{band_ja}</div>
        <div class="band-en">{band_en}</div>
        <div class="index">{index_line}</div>
      </div>
    </div>
    <div class="footer">
      <div class="site">{site_domain}</div>
      <div class="disc">情報提供目的の自作指標です。投資助言ではありません。</div>
    </div>
  </div>
</body></html>"""


def render_card(latest: dict, out_path: str, site_domain: str = "") -> str:
    """latest（1版）からゲージPNGを out_path に書き出してパスを返す。"""
    import os

    from playwright.sync_api import sync_playwright

    html = build_html(latest, site_domain=site_domain)
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    # ローカル検証用に、既定と別ビルドの chromium を使う場合のみ実行ファイルを上書きできる
    # （CI では `playwright install chromium` が一致するブラウザを入れるため未設定でよい）。
    exe = os.environ.get("PLAYWRIGHT_CHROMIUM_PATH")
    launch_kwargs = {"executable_path": exe} if exe else {}
    with sync_playwright() as p:
        browser = p.chromium.launch(**launch_kwargs)
        try:
            page = browser.new_page(viewport={"width": 1200, "height": 675},
                                    device_scale_factor=2)
            page.set_content(html, wait_until="networkidle")
            page.locator(".card").screenshot(path=str(out))
        finally:
            browser.close()
    return str(out)


def load_latest(variant: str) -> dict:
    path = DATA_DIR / f"latest.{variant}.json"
    if not path.exists():  # 既定版は latest.json も兼ねる
        path = DATA_DIR / "latest.json"
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser(description="Fear & Greed ゲージ画像(PNG)生成")
    ap.add_argument("--variant", default="nikkei225")
    ap.add_argument("--out", default=str(Path(tempfile.gettempdir()) / "fgi_card.png"))
    ap.add_argument("--site", default="", help="フッターに出すサイトのドメイン")
    args = ap.parse_args()
    latest = load_latest(args.variant)
    path = render_card(latest, args.out, site_domain=args.site)
    print(f"wrote {path}  (score={latest.get('score')} band={latest.get('band')})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
