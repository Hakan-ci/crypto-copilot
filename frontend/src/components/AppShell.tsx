"use client";

import clsx from "clsx";
import {
  BarChart3,
  BookOpenCheck,
  Cable,
  Download,
  ListChecks,
  Settings
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { ReactNode, useState } from "react";

import { useDevelopmentUserId } from "@/lib/storage";

const navigation = [
  { href: "/dashboard", label: "Dashboard", icon: BarChart3 },
  { href: "/connect-mexc", label: "Connect MEXC", icon: Cable },
  { href: "/import-history", label: "Import History", icon: Download },
  { href: "/positions", label: "Positions", icon: ListChecks },
  { href: "/settings/trading-plan", label: "Trading Plan", icon: BookOpenCheck }
];

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { userId, setUserId, isReady } = useDevelopmentUserId();
  const [draftUserId, setDraftUserId] = useState("");

  function handleSaveUserId() {
    setUserId(draftUserId || userId);
  }

  return (
    <div className="min-h-screen">
      <aside className="fixed inset-y-0 left-0 hidden w-64 border-r border-stone-200 bg-white/95 px-4 py-5 lg:block">
        <div className="mb-8">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-teal-700">
            MEXC Futures
          </p>
          <h1 className="mt-2 text-xl font-semibold text-slate-950">Trade Review</h1>
          <p className="mt-2 text-sm text-slate-600">Read-only journal and review workspace.</p>
        </div>
        <nav className="space-y-1">
          {navigation.map((item) => {
            const isActive =
              pathname === item.href || (item.href !== "/dashboard" && pathname.startsWith(item.href));
            const Icon = item.icon;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={clsx(
                  "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition",
                  isActive
                    ? "bg-teal-50 text-teal-800"
                    : "text-slate-600 hover:bg-stone-100 hover:text-slate-950"
                )}
              >
                <Icon className="h-4 w-4" aria-hidden="true" />
                {item.label}
              </Link>
            );
          })}
        </nav>
      </aside>

      <div className="lg:pl-64">
        <header className="sticky top-0 z-20 border-b border-stone-200 bg-white/90 px-4 py-3 backdrop-blur md:px-6">
          <div className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
            <nav className="flex gap-2 overflow-x-auto lg:hidden">
              {navigation.map((item) => {
                const Icon = item.icon;
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className="inline-flex h-10 w-10 flex-none items-center justify-center rounded-md border border-stone-200 bg-white text-slate-700"
                    aria-label={item.label}
                    title={item.label}
                  >
                    <Icon className="h-4 w-4" aria-hidden="true" />
                  </Link>
                );
              })}
            </nav>
            <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between xl:flex-1">
              <div>
                <p className="text-sm font-semibold text-slate-950">Review mode only</p>
                <p className="text-xs text-slate-600">
                  The frontend calls your backend for history, analytics, and AI reviews.
                </p>
              </div>
              <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
                <label className="text-xs font-medium text-slate-600" htmlFor="dev-user-id">
                  Development user ID
                </label>
                <input
                  id="dev-user-id"
                  className="h-9 w-full rounded-md border border-stone-300 bg-white px-3 text-sm outline-none focus:border-teal-600 sm:w-80"
                  placeholder={isReady && userId ? userId : "Paste UUID from backend"}
                  value={draftUserId}
                  onChange={(event) => setDraftUserId(event.target.value)}
                />
                <button
                  className="inline-flex h-9 items-center justify-center gap-2 rounded-md bg-slate-900 px-3 text-sm font-medium text-white hover:bg-slate-800"
                  type="button"
                  onClick={handleSaveUserId}
                >
                  <Settings className="h-4 w-4" aria-hidden="true" />
                  Save
                </button>
              </div>
            </div>
          </div>
        </header>
        <main className="mx-auto max-w-7xl px-4 py-6 md:px-6">{children}</main>
      </div>
    </div>
  );
}
