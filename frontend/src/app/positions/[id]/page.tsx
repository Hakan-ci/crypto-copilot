"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BarChart3, RefreshCw } from "lucide-react";
import { useParams } from "next/navigation";
import { useState } from "react";

import { CandlestickChart } from "@/components/CandlestickChart";
import { EmptyState } from "@/components/EmptyState";
import { IndicatorSnapshotPanel } from "@/components/IndicatorSnapshotPanel";
import { MetricCard } from "@/components/MetricCard";
import { RiskWarnings } from "@/components/RiskWarnings";
import { TimeframeSelector } from "@/components/TimeframeSelector";
import { TradeReviewPanel } from "@/components/TradeReviewPanel";
import { calculateIndicatorSnapshots, getPositionDetail } from "@/lib/api";
import { classForPnl, formatCurrency, formatDateTime, formatDecimal } from "@/lib/format";
import { TIMEFRAMES } from "@/lib/timeframes";
import type { Timeframe } from "@/lib/types";

export default function PositionDetailPage() {
  const params = useParams<{ id: string }>();
  const positionId = params.id;
  const [selectedTimeframe, setSelectedTimeframe] = useState<Timeframe | "all">("all");
  const queryClient = useQueryClient();
  const detailQuery = useQuery({
    queryKey: ["position-detail", positionId],
    queryFn: () => getPositionDetail(positionId),
    enabled: Boolean(positionId)
  });
  const snapshotMutation = useMutation({
    mutationFn: () =>
      calculateIndicatorSnapshots(
        positionId,
        TIMEFRAMES.map((timeframe) => timeframe.value)
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["position-detail", positionId] });
    }
  });

  if (detailQuery.isLoading) {
    return <EmptyState title="Loading position">Reading position detail and snapshots.</EmptyState>;
  }

  if (detailQuery.isError) {
    return (
      <EmptyState title="Position could not load">{(detailQuery.error as Error).message}</EmptyState>
    );
  }

  const detail = detailQuery.data;
  if (!detail) {
    return <EmptyState title="Position not found">This position is not available.</EmptyState>;
  }

  const { position, indicator_snapshots: snapshots } = detail;
  const visibleSnapshots =
    selectedTimeframe === "all"
      ? snapshots
      : snapshots.filter((snapshot) => snapshot.timeframe === selectedTimeframe);

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-slate-950">{position.symbol}</h1>
          <p className="mt-1 text-sm text-slate-600">
            {position.direction.toUpperCase()} position opened {formatDateTime(position.opened_at)}
          </p>
        </div>
        <button
          className="inline-flex h-10 items-center justify-center gap-2 rounded-md border border-stone-300 bg-white px-4 text-sm font-medium text-slate-800 hover:bg-stone-100 disabled:cursor-not-allowed disabled:text-slate-400"
          type="button"
          disabled={snapshotMutation.isPending}
          onClick={() => snapshotMutation.mutate()}
        >
          <RefreshCw className="h-4 w-4" aria-hidden="true" />
          {snapshotMutation.isPending ? "Refreshing..." : "Calculate snapshots"}
        </button>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard label="Status" value={position.status} helper="Current reconstructed state." />
        <MetricCard
          label="Entry"
          value={formatDecimal(position.avg_entry_price, 4)}
          helper={`Volume ${formatDecimal(position.total_volume, 4)}`}
        />
        <MetricCard
          label="Exit"
          value={formatDecimal(position.avg_exit_price, 4)}
          helper={`Closed ${formatDateTime(position.closed_at)}`}
        />
        <MetricCard
          label="Realized PnL"
          value={formatCurrency(position.realized_pnl)}
          helper={`Fees ${formatCurrency(position.total_fees)}`}
          tone={
            classForPnl(position.realized_pnl).includes("emerald")
              ? "positive"
              : classForPnl(position.realized_pnl).includes("red")
                ? "negative"
                : "neutral"
          }
        />
      </div>

      {snapshotMutation.isError ? (
        <EmptyState title="Snapshots could not be calculated">
          {(snapshotMutation.error as Error).message}
        </EmptyState>
      ) : null}
      {snapshotMutation.data?.warnings.length ? (
        <div className="rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          {snapshotMutation.data.warnings.join(" ")}
        </div>
      ) : null}

      <section className="space-y-3">
        <div className="flex items-center gap-2">
          <BarChart3 className="h-5 w-5 text-teal-700" aria-hidden="true" />
          <h2 className="text-lg font-semibold text-slate-950">Chart</h2>
        </div>
        <CandlestickChart />
      </section>

      <RiskWarnings position={position} snapshots={snapshots} />

      <section className="space-y-3">
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-lg font-semibold text-slate-950">Indicator snapshots</h2>
          <TimeframeSelector
            value={selectedTimeframe}
            onChange={setSelectedTimeframe}
            includeAll
          />
        </div>
        {visibleSnapshots.length === 0 ? (
          <EmptyState title="No snapshots yet">
            Calculate snapshots after candles are stored for 1H, 4H, and 1D.
          </EmptyState>
        ) : (
          <div className="grid gap-4">
            {visibleSnapshots.map((snapshot) => (
              <IndicatorSnapshotPanel key={snapshot.id} snapshot={snapshot} />
            ))}
          </div>
        )}
      </section>

      <TradeReviewPanel positionId={position.id} review={detail.ai_review} />
    </div>
  );
}
