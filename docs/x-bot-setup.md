# X（Twitter）自動投稿 BOT セットアップ手順

日次 cron（`.github/workflows/daily.yml`, JST 06:00 平日）でスコアを再生成した直後に、
**日経225版のスコアをゲージ画像＋サイトURL付きで X に自動投稿**する仕組みのセットアップ。
コードは実装済みで、**以下の認証情報を GitHub に登録すれば自動で動き出す**（未登録の間は
投稿ステップが自己スキップするので、日次スコア生成は影響を受けない）。

- 画像生成：`engine/scripts/x_card.py`（Playwright でゲージ PNG を描画）
- 投稿本体：`engine/scripts/post_to_x.py`（tweepy で画像アップロード＋ツイート）
- 重複ガード：`web/public/data/x_last_posted.json`（`as_of` が進んだ時だけ投稿）

---

## 0. 前提・ポリシー確認（重要）

- X の **Automation ルール上、自動投稿は許可**されている。ただし：
  - **自動アカウントであることをプロフィールで明示**すること（初日から必須）。
    X の設定 → アカウント →「自動化」でラベル付け（管理者アカウントを紐付け）する。
  - 内容は**独自・非スパム**であること（日1回の指数更新は適合）。
  - **AI 生成の“返信”**は事前承認が必要。本 BOT は**自分の投稿のみで返信はしない**ため対象外。
- **無料 API 枠**で画像アップロード込み **月約 500 投稿**まで可能。日1回（月約30）は無料枠内。
  → 有料ティア不要。

---

## 1. 投稿用アカウントを用意（推奨：専用アカウント）

普段使いのアカウントと分けた **BOT 専用アカウント**を推奨。プロフィールに「自動アカウント」
ラベルを付け、bio に「本指標の自動投稿 bot。投資助言ではありません」等を明記する。

## 2. X 開発者ポータルで App を作成

1. https://developer.x.com/ にログイン（投稿用アカウントで）→ 開発者登録（Free）。
2. **Project + App** を作成。
3. App の **User authentication settings** を編集：
   - **App permissions**: **Read and Write**（投稿に必須。Read only では投稿できない）
   - **Type of App**: Web App / Automated App（Bot）
   - Callback URL / Website URL は任意のもの（例：サイトの URL）を入れる。
4. **Keys and tokens** タブで次の 4 つを取得（Write 権限を付けた**後**に Access Token を再生成）：
   - **API Key**（= Consumer Key）
   - **API Key Secret**（= Consumer Secret）
   - **Access Token**
   - **Access Token Secret**

> Access Token は「App permissions = Read and Write」に変更した**後**に発行し直すこと。
> 変更前に発行したトークンは Read 権限のままで、投稿時に 403 になる。

## 3. GitHub に登録

対象リポジトリの **Settings → Secrets and variables → Actions**：

**Secrets（Repository secrets）** に 4 つ：

| Secret 名 | 値 |
| --- | --- |
| `X_API_KEY` | API Key |
| `X_API_SECRET` | API Key Secret |
| `X_ACCESS_TOKEN` | Access Token |
| `X_ACCESS_SECRET` | Access Token Secret |

**Variables（Repository variables）** に 1 つ（任意だが推奨。投稿本文と画像フッターの URL）：

| Variable 名 | 値（例） |
| --- | --- |
| `SITE_URL` | `https://<あなたのサイト>` |

## 4. 動作確認

- **手動起動**：Actions →「日次スコア再生成」→ **Run workflow**（mode=real）。
  実行後、BOT アカウントにゲージ画像付きのツイートが出れば成功。
  `web/public/data/x_last_posted.json` が更新される（＝次回同 `as_of` では投稿しない）。
- **翌朝の cron**：平日 JST 06:00 に自動投稿。`as_of` が前日から進んでいれば投稿、
  祝日等で進んでいなければスキップ（重複投稿しない）。

## 5. 投稿内容の調整

- 本文テンプレ：`engine/scripts/post_to_x.py` の `build_tweet_text()`。
- 画像レイアウト・配色：`engine/scripts/x_card.py`（Web 版ゲージと同じ幾何・配色）。
- ローカルで画像だけ確認：
  ```bash
  cd engine
  python scripts/x_card.py --site "example.com" --out /tmp/card.png
  # 本文＋画像をAPIなしで確認（--dry-run は X API を呼ばない）
  SITE_URL="https://example.com" python scripts/post_to_x.py --dry-run
  ```

## トラブルシュート

- **403 Forbidden（投稿時）**：App permissions が Read only か、Write 化前の古い
  Access Token を使っている。Read and Write に変更 → Access Token を再生成 → Secrets 更新。
- **画像の日本語が □（豆腐）になる**：CI では `fonts-noto-cjk` を導入済み。ローカルで出る
  場合は日本語フォント（Noto Sans CJK / IPAGothic 等）を入れる。
- **投稿されない/スキップされる**：Secrets 未設定（ログに「認証情報が未設定」）、または
  `as_of` が前回投稿から進んでいない（ログに「投稿済み。更新なしのためスキップ」）。
- **無料枠の上限**：月約500投稿。日1回運用なら余裕。短時間の連続 `Run workflow` は避ける。
