import type { Metadata } from "next";
import { Analytics } from "@vercel/analytics/next";
import "./globals.css";

export const metadata: Metadata = {
  title: "日本版 Fear & Greed Index｜投資家心理指数",
  description:
    "日本株式市場の投資家心理を8指標から0〜100の単一スコアに合成する自作インデックス。情報提供目的であり投資助言ではありません。",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ja">
      <body>
        {children}
        <Analytics />
      </body>
    </html>
  );
}
