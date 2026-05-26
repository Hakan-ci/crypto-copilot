import type { Metadata } from "next";

import { AppShell } from "@/components/AppShell";
import { Providers } from "@/app/providers";
import "./globals.css";

export const metadata: Metadata = {
  title: "MEXC Futures Trade Review",
  description: "Read-only MEXC Futures trade-review co-pilot"
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <Providers>
          <AppShell>{children}</AppShell>
        </Providers>
      </body>
    </html>
  );
}
