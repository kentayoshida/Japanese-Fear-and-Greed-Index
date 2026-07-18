"""#6 信用評価損益率（買い方）を松井証券「投資指標（店内）」から取得。仕様 §2。

このページは値が生HTML・単独XHRに存在せず（Network検索で該当なし）、描画後の DOM に
のみ現れるため、ヘッドレスブラウザ（Playwright）でレンダリングして抽出する。
ToS 確認済み（前営業日更新分は利用制限なし・Ken確認）。取得は日次1回に限ること。

抽出対象：「信用残速報」テーブルの『買い残』行の『評価損益率(%)』セル（例 -3.856）と、
そのテーブルが示す **基準日**（データ本来の日付）。松井は評価損益率を「翌営業日に公開」する
（祝日が絡むと更に遅延する）ため、実行日ではなく **ページの基準日** を系列のキーに使う。
基準日を確実に読めなかった場合は None を返し、呼び出し側はその回の格納を見送る
（日付を推測して捏造しない）。

JS描画が遅く wait_for_selector が時折 Timeout するため、試行ごとに新しいコンテキストで
待ち時間を延ばしながら数回リトライする（tier-1 の実測点＝較正の要のため取りこぼしを減らす）。
"""

from __future__ import annotations

import datetime as _dt
import re
import time

import pandas as pd

from .base import FetchError

URL = "https://www.matsui.co.jp/market/stock/netstock-info/"

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# 基準日の許容範囲（今日から何日前まで遡って妥当とみなすか）。祝日連休でも 45 日あれば十分。
_MAX_BASIS_AGE_DAYS = 45

# 見出し（テーブル本体より早く安定描画される）の出現待ち上限。見出しは通常数秒で出るため、
# ここで頭打ちにして、完全ブロック時は買い残行の満額待ちに入る前に早めに失敗→次リトライへ。
_HEADING_TIMEOUT_MS = 20000


def _parse_pl(text: str | None) -> float:
    """『買い残』行の評価損益率セル文字列から数値(%)を取り出して検証する。"""
    if not text:
        raise FetchError("margin_pl: 評価損益率セルを取得できず")
    m = re.search(r"-?\d+(?:\.\d+)?", text.replace(",", ""))
    if not m:
        raise FetchError(f"margin_pl: 値を解釈できず '{text}'")
    value = float(m.group())
    if not (-60.0 <= value <= 60.0):  # 信用評価損益率の常識的レンジ
        raise FetchError(f"margin_pl: 想定外の値 {value}")
    return value


# 松井の基準日は「信用取引指標(松井証券店内)」見出しの右に "7/16(木)" 形式で表示される。
# 曜日サフィックス（例 "(木)"）は基準日ラベルの定型で、他の数値と区別する強い手掛かり。
_WD = "日月火水木金土"
# 曜日付き（最優先・ページ全体から拾っても安全）。年あり/年なしの両対応。
_RE_YMD_WD = re.compile(
    r"(20\d{2})\s*[./年\-]\s*(\d{1,2})\s*[./月\-]\s*(\d{1,2})\s*日?\s*[（(]\s*[" + _WD + r"]\s*[）)]"
)
_RE_MD_WD = re.compile(
    r"(?<!\d)(\d{1,2})\s*[/月]\s*(\d{1,2})\s*日?\s*[（(]\s*[" + _WD + r"]\s*[）)]"
)
# 曜日なし（近傍テキストのフォールバック用）。完全な年月日 / 年なし。
_RE_YMD = re.compile(r"(20\d{2})\s*[./年\-]\s*(\d{1,2})\s*[./月\-]\s*(\d{1,2})")
_RE_MD = re.compile(r"(?<!\d)(\d{1,2})\s*[./月]\s*(\d{1,2})\s*日?")


def _extract_basis_date(
    text: str | None, today: _dt.date | None = None, require_weekday: bool = False
) -> pd.Timestamp | None:
    """テキストから基準日らしき日付を抽出する。

    未来でなく、直近 _MAX_BASIS_AGE_DAYS 日以内で最も新しい日付を採用する。年なし表記は
    今年/前年を当てはめて妥当な方を選ぶ。妥当な候補が無ければ None（＝日付を推測しない）。
    require_weekday=True のときは曜日サフィックス付きの日付（例 "7/16(木)"）のみを対象にする
    （ページ全体を走査しても誤検出しにくい）。
    """
    if not text:
        return None
    today = today or (_dt.datetime.utcnow() + _dt.timedelta(hours=9)).date()
    re_ymd, re_md = (_RE_YMD_WD, _RE_MD_WD) if require_weekday else (_RE_YMD, _RE_MD)
    candidates: list[_dt.date] = []
    for m in re_ymd.finditer(text):
        try:
            candidates.append(_dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3))))
        except ValueError:
            continue
    for m in re_md.finditer(text):
        mo, d = int(m.group(1)), int(m.group(2))
        for y in (today.year, today.year - 1):
            try:
                candidates.append(_dt.date(y, mo, d))
            except ValueError:
                continue
    best: _dt.date | None = None
    for dt in candidates:
        if dt > today:
            continue
        if (today - dt).days > _MAX_BASIS_AGE_DAYS:
            continue
        if best is None or dt > best:
            best = dt
    return pd.Timestamp(best) if best else None


def _basis_date_from_page(page) -> pd.Timestamp | None:
    """ページから基準日を読み取る（読めなければ None）。

    1) ページ全体から曜日付き日付（"7/16(木)" 形式＝基準日ラベルの定型）を最優先で拾う。
    2) 取れなければ、基準日を伴いやすい見出し近傍のテキストから通常日付を拾う。
    """
    # 1) 曜日付き日付（最優先）。まず「信用取引指標/信用残速報」見出しの直近ブロックを狙い、
    #    取れなければページ全体を走査（曜日サフィックスがあるので全体走査でも誤検出しにくい）。
    region_texts: list[str] = []
    for head in ("信用取引指標", "信用残速報"):
        try:
            blk = page.locator(
                f"xpath=//*[contains(text(),'{head}')]"
                f"/ancestor-or-self::*[self::section or self::div or self::header][1]"
            )
            if blk.count():
                region_texts.append(blk.first.inner_text())
        except Exception:  # noqa: BLE001
            continue
    try:
        body = page.locator("body").inner_text()
    except Exception:  # noqa: BLE001
        body = ""
    for txt in [*region_texts, body]:
        d = _extract_basis_date(txt, require_weekday=True)
        if d is not None:
            return d

    # 2) フォールバック：見出し/キーワード近傍の通常日付（曜日なし）
    blobs: list[str] = []
    try:
        anc = page.locator(
            "xpath=//tr[contains(., '買い残')]/ancestor::*[self::section or self::div][1]"
        )
        if anc.count():
            blobs.append(anc.first.inner_text())
    except Exception:  # noqa: BLE001
        pass
    for kw in ("信用取引指標", "信用残速報", "信用残", "店内", "基準日", "時点"):
        try:
            loc = page.locator(f"text={kw}")
            for i in range(min(loc.count(), 3)):
                blobs.append(loc.nth(i).inner_text())
        except Exception:  # noqa: BLE001
            continue
    for blob in blobs:
        d = _extract_basis_date(blob)
        if d is not None:
            return d
    return None


def _wait_for_heading(page, timeout_ms: int) -> None:
    """テーブル本体より早く安定描画される見出しの出現を待つ（段階待ちの前段）。

    「信用取引指標」または「信用残速報」のいずれかが出れば通過。買い残行を直接待つ前に
    ここを挟むことで、描画が進んでいるかを早期に判定でき、ページ全体がブロック/未描画の
    ときは満額の行待ちに入らず早めに失敗して次リトライへ回せる。
    """
    page.wait_for_selector(
        "xpath=//*[contains(text(),'信用取引指標') or contains(text(),'信用残速報')]",
        timeout=timeout_ms,
    )


def _scrape_once(
    browser, selector_timeout_ms: int, goto_timeout_ms: int
) -> tuple[float, pd.Timestamp | None]:
    """1回ぶんの取得。『買い残』行の評価損益率(%)と、ページ上の基準日を返す。"""
    # ※ 松井ページは分析タグが常時通信し networkidle に到達しないため使わない。
    #   load（全リソース読込完了）まで待ってから、見出し→テーブル行の順に段階的に待つ。
    context = browser.new_context(user_agent=_UA)
    try:
        page = context.new_page()
        page.goto(URL, wait_until="load", timeout=goto_timeout_ms)
        # まず見出し（早く安定描画される）を待ち、描画が進んでいることを確認してから
        _wait_for_heading(page, min(selector_timeout_ms, _HEADING_TIMEOUT_MS))
        # 「買い残」を含む行（信用残速報テーブル）が描画されるまで待つ
        page.wait_for_selector("tr:has-text('買い残')", timeout=selector_timeout_ms)
        row = page.locator("tr", has_text="買い残").first
        # 買い残行の td: [0]=信用残(億円), [1]=評価損益率(%)
        text = row.locator("td").nth(1).inner_text()
        value = _parse_pl(text)
        basis = _basis_date_from_page(page)
        return value, basis
    finally:
        context.close()


def fetch_margin_pl_buy(
    timeout_ms: int = 60000, attempts: int = 3, selector_timeout_ms: int = 45000
) -> tuple[float, pd.Timestamp | None]:
    """松井『投資指標(店内)』の信用評価損益率（買い方, %）と基準日を返す。

    返り値: (評価損益率%, 基準日 or None)。基準日はページ表示の値（データ本来の日付）で、
    読めなかった場合は None（呼び出し側は格納を見送る）。

    attempts 回まで再試行し、試行ごとにセレクタ待ちを延長（描画遅延に頑健化）。
    すべて失敗したら最後のエラーを添えて FetchError を送出する。
    """
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # noqa: BLE001
        raise FetchError(f"margin_pl: playwright 未導入（{exc}）") from exc

    last_err: Exception | None = None
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            for attempt in range(1, attempts + 1):
                # 試行が進むごとに待ち時間を延長（例 45s → 60s → 75s）
                sel_timeout = selector_timeout_ms + (attempt - 1) * 15000
                try:
                    return _scrape_once(browser, sel_timeout, timeout_ms)
                except FetchError as exc:
                    last_err = exc
                except Exception as exc:  # noqa: BLE001  Timeout 等
                    last_err = exc
                if attempt < attempts:
                    time.sleep(2 * attempt)  # 2s, 4s のバックオフ
        finally:
            browser.close()

    raise FetchError(f"margin_pl: {attempts}回試行して取得失敗（最後のエラー: {last_err}）")
