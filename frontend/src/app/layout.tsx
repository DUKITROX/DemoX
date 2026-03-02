import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "DemoX — AI-Powered Website Demos",
  description: "Get a live, narrated demo of any website powered by AI",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="antialiased">{children}</body>
    </html>
  );
}
