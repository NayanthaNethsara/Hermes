import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

import { APP_NAME, TEAM_NAME, APP_DESCRIPTION } from "@/lib/constants";

const inter = Inter({ subsets: ["latin"], variable: "--font-sans" });

export const metadata: Metadata = {
  title: `${APP_NAME} | ${TEAM_NAME}`,
  description: APP_DESCRIPTION,
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`h-full dark ${inter.variable} font-sans`}
    >
      <body className="flex min-h-full flex-col bg-[#131314] text-[#e3e3e3] antialiased">
        {children}
      </body>
    </html>
  );
}
