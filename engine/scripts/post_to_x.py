#!/usr/bin/env python3
"""日次 Fear & Greed 指数（日経225版）を X（Twitter）へゲージ画像付きで投稿する。

日次 cron（daily.yml）が `run_daily.py` でスコアを再生成した直後に呼ぶ。手順：
  1) `latest.nikkei225.json` を読む
  2) 重複ガード：状態ファイルの as_of と同じなら「更新なし」として投稿せず終了
     （祝日など指数が進まない朝は再投稿しない — Ken 指定）
  3) `x_card.render_card` でゲージ PNG を生成
  4) 本文（日本語・URL・免責・ハッシュタグ）を組み立て
  5) tweepy でメディアアップロード → ツイート作成（OAuth1.0a ユーザーコンテキスト）
  6) 成功したら状態ファイルを更新

安全側の設計：
- X の認証情報（環境変数）が未設定なら、投稿せずログを出して正常終了する
  （Secrets 未設定の環境でも daily を壊さない）。
- `--dry-run` は画像生成と本文出力までで、API を一切呼ばない（クレデンシャル不要で検証可）。

認証情報（GitHub Secrets で設定・コードに直書きしない）:
  X_API_KEY / X_API_SECRET / X_ACCESS_TOKEN / X_ACCESS_SECRET
サイトURL（GitHub Variables 推奨）:
  SITE_URL  例: https://japan-fgi.vercel.app
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

# 同ディレクトリの x_card を import 可能に
SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

import x_card  # noqa: E402

DEFAULT_STATE_PATH = x_card.DATA_DIR / "x_last_posted.json"

_CRED_KEYS = ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_SECRET")


def _weighted_len(text: str) -> int:
    """X の文字数カウント近似：CJK・全角は2、その他は1で数える。"""
    total = 0
    for ch in text:
        total += 2 if ord(ch) > 0x1100 else 1
    return total


def build_tweet_text(latest: dict, site_url: str) -> str:
    """投稿本文を組み立てる（280 の重み付き文字数に収める）。"""
    score = latest.get("score")
    score_txt = str(round(float(score))) if score is not None else "—"
    band_ja = latest.get("band_label_ja", "")
    band_en = latest.get("band", "")
    variant_label = latest.get("variant_label") or "日経225"
    short_date = x_card._short_date(latest.get("as_of", ""))
    index_label = latest.get("index_label", variant_label)
    index_value = latest.get("index_value")

    lines = [
        f"日本版 Fear & Greed 指数（{variant_label}）",
        f"{short_date}時点：{score_txt} {band_ja}（{band_en}）",
    ]
    if index_value is not None:
        lines.append(f"{index_label}: {index_value:,.2f}")
    if site_url:
        lines += ["", f"詳しく見る → {site_url}"]
    tail = "\n\n#日本株 #日経平均 #FearAndGreed"

    text = "\n".join(lines) + tail
    if _weighted_len(text) > 280:  # 収まらなければハッシュタグ行を落とす
        text = "\n".join(lines)
    return text


def _load_state(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001  壊れていたら空扱いで作り直す
            return {}
    return {}


def _already_posted(state: dict, variant: str, as_of: str) -> bool:
    return bool(as_of) and state.get(variant, {}).get("as_of") == as_of


def _write_state(path: Path, state: dict, variant: str, as_of: str) -> None:
    state[variant] = {"as_of": as_of, "posted_at": datetime.now(timezone.utc).isoformat()}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _post_to_x(image_path: str, text: str) -> str:
    """tweepy でメディアアップロード → ツイート作成。作成したツイートIDを返す。"""
    import tweepy

    api_key = os.environ["X_API_KEY"]
    api_secret = os.environ["X_API_SECRET"]
    access_token = os.environ["X_ACCESS_TOKEN"]
    access_secret = os.environ["X_ACCESS_SECRET"]

    # 画像アップロードは v1.1 media/upload（OAuth1.0a）
    auth = tweepy.OAuth1UserHandler(api_key, api_secret, access_token, access_secret)
    api_v1 = tweepy.API(auth)
    media = api_v1.media_upload(filename=image_path)

    # ツイート作成は v2 create_tweet
    client = tweepy.Client(
        consumer_key=api_key,
        consumer_secret=api_secret,
        access_token=access_token,
        access_token_secret=access_secret,
    )
    resp = client.create_tweet(text=text, media_ids=[media.media_id])
    return str(resp.data.get("id"))


def main() -> int:
    ap = argparse.ArgumentParser(description="Fear & Greed 指数を X に自動投稿")
    ap.add_argument("--variant", default="nikkei225")
    ap.add_argument("--dry-run", action="store_true",
                    help="画像生成と本文出力のみ。X API を呼ばない")
    ap.add_argument("--force", action="store_true",
                    help="重複ガードを無視して投稿（同一 as_of でも実行）")
    ap.add_argument("--state", default=str(DEFAULT_STATE_PATH))
    ap.add_argument("--image", default=str(Path(tempfile.gettempdir()) / "fgi_x_card.png"))
    args = ap.parse_args()

    latest = x_card.load_latest(args.variant)
    as_of = latest.get("as_of", "")
    state_path = Path(args.state)
    state = _load_state(state_path)

    # 重複ガード（Ken 指定：as_of が進んだ時だけ投稿）
    if not args.force and _already_posted(state, args.variant, as_of):
        print(f"[skip] {args.variant}: as_of={as_of} は投稿済み。更新なしのためスキップ。")
        return 0

    site_url = os.environ.get("SITE_URL", "").strip()
    site_domain = urlparse(site_url).netloc if site_url else ""
    text = build_tweet_text(latest, site_url)

    # 画像生成（dry-run でも作って中身を確認できるように）
    image_path = x_card.render_card(latest, args.image, site_domain=site_domain)

    print("---- tweet text ----")
    print(text)
    print(f"---- weighted length: {_weighted_len(text)}/280 ----")
    print(f"image: {image_path}")

    if args.dry_run:
        print("[dry-run] X API は呼び出しませんでした。")
        return 0

    missing = [k for k in _CRED_KEYS if not os.environ.get(k)]
    if missing:
        print(f"[skip] X 認証情報が未設定のため投稿しません（未設定: {', '.join(missing)}）。")
        return 0

    tweet_id = _post_to_x(image_path, text)
    print(f"[posted] tweet id={tweet_id}")
    _write_state(state_path, state, args.variant, as_of)
    print(f"[state] {state_path} を更新（as_of={as_of}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
