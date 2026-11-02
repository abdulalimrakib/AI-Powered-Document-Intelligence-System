import type React from "react";
import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { ThemeProvider } from "@/_providers/themeProvider";
import { Toaster } from "sonner";
import Navbar from "@/components/navbar";

const inter = Inter({
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "DocIntel",
  description: "AI document intelligence: extract, validate and search invoices and financial documents",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={inter.className}>
        <ThemeProvider attribute="class" defaultTheme="system" enableSystem disableTransitionOnChange>
          <Navbar />
          <main className="mx-auto max-w-7xl px-4 py-8">{children}</main>
          <Toaster richColors />
        </ThemeProvider>
      </body>
    </html>
  );
}
