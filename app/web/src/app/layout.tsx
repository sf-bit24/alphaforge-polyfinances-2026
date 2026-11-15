import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";
import { Footer } from "@/components/layout/footer";
import { Header } from "@/components/layout/header";
import { ResponsibleBanner } from "@/components/layout/banner";
import { SessionProvider } from "@/lib/client/session";
import { I18nProvider } from "@/lib/i18n/provider";
import { serverDictionary } from "@/lib/i18n/server";
import "./globals.css";

export async function generateMetadata(): Promise<Metadata> {
  const { t } = await serverDictionary();
  return {
    title: { default: "AlphaForge AI", template: "%s · AlphaForge AI" },
    description: t.meta.description,
    robots: { index: false, follow: false },
  };
}

export const viewport: Viewport = {
  themeColor: "#0a1222",
};

export default async function RootLayout({ children }: { children: ReactNode }) {
  const { locale } = await serverDictionary();
  return (
    <html lang={locale}>
      <body className="flex min-h-dvh flex-col font-sans antialiased">
        <I18nProvider initialLocale={locale}>
          <SessionProvider>
            <Header />
            <ResponsibleBanner />
            <main id="main" tabIndex={-1} className="flex flex-1 flex-col focus:outline-none">
              {children}
            </main>
            <Footer />
          </SessionProvider>
        </I18nProvider>
      </body>
    </html>
  );
}
