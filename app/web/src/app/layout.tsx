import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";
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
  themeColor: "#ffffff",
};

/**
 * Providers only: the journey (/) draws its own full-screen scene and top bar,
 * the other screens get the navigation from app/(app)/layout.tsx.
 */
export default async function RootLayout({ children }: { children: ReactNode }) {
  const { locale } = await serverDictionary();
  return (
    <html lang={locale}>
      <body className="font-sans antialiased">
        <I18nProvider initialLocale={locale}>
          <SessionProvider>{children}</SessionProvider>
        </I18nProvider>
      </body>
    </html>
  );
}
