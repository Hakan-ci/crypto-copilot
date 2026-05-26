"use client";

import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  BadgeDollarSign,
  CircleDollarSign,
  Percent,
  ReceiptText,
  TrendingDown,
  TrendingUp
} from "lucide-react";

import { EmptyState } from "@/components/EmptyState";
import { MetricCard } from "@/components/MetricCard";
import { getDashboard } from "@/lib/api";
import { classForPnl, formatCurrency, formatDecimal, formatPercent } from "@/lib/format";
import { useDevelopmentUserId } from "@/lib/storage";

export default function DashboardPage() {
  const { userId, isReady } = useDevelopmentUserId();
  const dashboardQuery = useQuery({
    queryKey: ["dashboard", userId],
    queryFn: () => getDashboard(userId),
    enabled: Boolean(userId)
  });

  if (!isReady) {
    return <EmptyState title="Loading workspace">Preparing your local workspace.</EmptyState>;
  }

  if (!userId) {
    return (
      <EmptyState title="Add a development user ID">
        Paste a backend user UUID in the header so the dashboard knows which reconstructed positions
        to read.
      </EmptyState>
    );
  }

  if (dashboardQuery.isLoading) {
    return <EmptyState title="Loading dashboard">Reading reconstructed MEXC Futures positions.</EmptyState>;
  }

  if (dashboardQuery.isError) {
    return (
      <EmptyState title="Dashboard could not load">
        {(dashboardQuery.error as Error).message}
      </EmptyState>
    );
  }

  const metrics = dashboardQuery.data;
  if (!metrics) {
    return <EmptyState title="No dashboard data">Import history and reconstruct positions first.</EmptyState>;
  }

  const cards = [
    {
      label: "Net PnL",
      value: formatCurrency(metrics.net_pnl),
      helper: "Realized PnL minus fees plus signed funding.",
      icon: CircleDollarSign,
      tone: classForPnl(metrics.net_pnl).includes("emerald")
        ? "positive"
        : classForPnl(metrics.net_pnl).includes("red")
          ? "negative"
          : "neutral"
    },
    {
      label: "Realized PnL",
      value: formatCurrency(metrics.total_realized_pnl),
      helper: "Closed-position PnL reported by MEXC fills.",
      icon: BadgeDollarSign,
      tone: "neutral"
    },
    {
      label: "Total fees",
      value: formatCurrency(metrics.total_fees),
      helper: "Trading fees from reconstructed positions.",
      icon: ReceiptText,
      tone: "warning"
    },
    {
      label: "Win rate",
      value: formatPercent(metrics.win_rate),
      helper: `${metrics.trade_count} closed positions reviewed.`,
      icon: Percent,
      tone: "neutral"
    },
    {
      label: "Average win",
      value: formatCurrency(metrics.average_win),
      helper: "Average net PnL of winning closed positions.",
      icon: TrendingUp,
      tone: "positive"
    },
    {
      label: "Average loss",
      value: formatCurrency(metrics.average_loss),
      helper: "Average net PnL of losing closed positions.",
      icon: TrendingDown,
      tone: "negative"
    },
    {
      label: "Profit factor",
      value: metrics.profit_factor ? formatDecimal(metrics.profit_factor, 3) : "-",
      helper: "Gross wins divided by absolute gross losses.",
      icon: Activity,
      tone: "neutral"
    }
  ] as const;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-slate-950">Dashboard</h1>
        <p className="mt-1 text-sm text-slate-600">
          Performance analytics from reconstructed MEXC Futures positions.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {cards.map((card) => (
          <MetricCard key={card.label} {...card} />
        ))}
        <MetricCard
          label="Position count"
          value={`${metrics.closed_positions} closed / ${metrics.open_positions} open`}
          helper="Open positions are shown separately from completed reviews."
          tone="neutral"
        />
      </div>

      <div className="grid gap-6 xl:grid-cols-3">
        <section>
          <h2 className="text-lg font-semibold text-slate-950">Best symbols</h2>
          <SymbolList symbols={metrics.best_symbols} />
        </section>
        <section>
          <h2 className="text-lg font-semibold text-slate-950">Worst symbols</h2>
          <SymbolList symbols={metrics.worst_symbols} />
        </section>
        <section>
          <h2 className="text-lg font-semibold text-slate-950">Indicator summary</h2>
          <div className="mt-3 space-y-2 rounded-md border border-stone-200 bg-white p-4 shadow-soft">
            {Object.entries(metrics.indicator_summary).map(([key, value]) => (
              <div key={key} className="flex items-center justify-between gap-4 text-sm">
                <span className="text-slate-600">{key.replaceAll("_", " ")}</span>
                <span className="font-semibold text-slate-950">{value}</span>
              </div>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}

function SymbolList({
  symbols
}: {
  symbols: Array<{ symbol: string; net_pnl: string; trade_count: number }>;
}) {
  if (symbols.length === 0) {
    return (
      <div className="mt-3 rounded-md border border-dashed border-stone-300 bg-white px-4 py-8 text-sm text-slate-600">
        No closed positions yet.
      </div>
    );
  }

  return (
    <div className="mt-3 divide-y divide-stone-100 rounded-md border border-stone-200 bg-white shadow-soft">
      {symbols.map((symbol) => (
        <div key={symbol.symbol} className="flex items-center justify-between gap-4 px-4 py-3">
          <div>
            <p className="font-medium text-slate-950">{symbol.symbol}</p>
            <p className="text-xs text-slate-500">{symbol.trade_count} closed positions</p>
          </div>
          <p className={`text-sm font-semibold ${classForPnl(symbol.net_pnl)}`}>
            {formatCurrency(symbol.net_pnl)}
          </p>
        </div>
      ))}
    </div>
  );
}
