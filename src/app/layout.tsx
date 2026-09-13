import type { Metadata } from "next";
import Footer from "@/components/Footer";
import "./globals.css";

export const metadata: Metadata = {
  title: "Kofun Atlas AI — 日本古墳時空間・地形・AI 分析アトラス",
  description:
    "公開・再利用可能なオープンデータだけを統合し、古墳の分布・年代・地形・AI 特徴量をブラウザ内で探索する静的アトラス。",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ja">
      <body>
        <main>{children}</main>
        <Footer />
      </body>
    </html>
  );
}
