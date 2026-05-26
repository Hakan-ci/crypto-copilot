"use client";

import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { EmptyState } from "@/components/EmptyState";
import { PositionsTable } from "@/components/PositionsTable";
import { TimeframeSelector } from "@/components/TimeframeSelector";
import { listPositions } from "@/lib/api";
import { useDevelopmentUserId } from "@/lib/storage";
import type { PositionDirection, PositionStatus, Timeframe } from "@/lib/types";

export default function PositionsPage() {
  const { userId, isReady } = useDevelopmentUserId();
  const [symbol, setSymbol] = useState("");
  const [status, setStatus] = useState<PositionStatus | "all">("all");
  const [direction, setDirection] = useState<PositionDirection | "all">("all");
  const [timeframe, setTimeframe] = useState<Timeframe | "all">("all");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");

  const filters = useMemo(
    () => ({
      symbol: symbol.trim().toUpperCase() || undefined,
      status: status === "all" ? undefined : status,
      direction: direction === "all" ? undefined : direction,
      timeframe: timeframe === "all" ? undefined : timeframe,
      start: start ? new Date(start).toISOString() : undefined,
      end: end ? new Date(end).toISOString() : undefined
    }),
    [direction, end, start, status, symbol, timeframe]
  );

  const positionsQuery = useQuery({
    queryKey: ["positions", userId, filters],
    queryFn: () => listPositions(userId, filters),
    enabled: Boolean(userId)
  });

  if (!isReady) {
    return <EmptyState title="Loading workspace">Preparing your local workspace.</EmptyState>;
  }

  if (!userId) {
    return (
      <EmptyState title="Add a development user ID">
        Paste a backend user UUID in the header to list reconstructed positions.
      </EmptyState>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-slate-950">Positions</h1>
        <p className="mt-1 text-sm text-slate-600">
          Reconstructed positions from imported MEXC Futures fills.
        </p>
      </div>

      <section className="space-y-4">
        <div className="grid gap-3 md:grid-cols-3 xl:grid-cols-6">
          <label className="block">
            <span className="text-sm font-medium text-slate-700">Symbol</span>
            <input
              className="mt-1 h-10 w-full rounded-md border border-stone-300 bg-white px-3 text-sm uppercase outline-none focus:border-teal-600"
              value={symbol}
              onChange={(event) => setSymbol(event.target.value)}
              placeholder="BTC_USDT"
            />
          </label>
          <label className="block">
            <span className="text-sm font-medium text-slate-700">Status</span>
            <select
              className="mt-1 h-10 w-full rounded-md border border-stone-300 bg-white px-3 text-sm outline-none focus:border-teal-600"
              value={status}
              onChange={(event) => setStatus(event.target.value as PositionStatus | "all")}
            >
              <option value="all">All</option>
              <option value="open">Open</option>
              <option value="closed">Closed</option>
            </select>
          </label>
          <label className="block">
            <span className="text-sm font-medium text-slate-700">Direction</span>
            <select
              className="mt-1 h-10 w-full rounded-md border border-stone-300 bg-white px-3 text-sm outline-none focus:border-teal-600"
              value={direction}
              onChange={(event) =>
                setDirection(event.target.value as PositionDirection | "all")
              }
            >
              <option value="all">All</option>
              <option value="long">Long</option>
              <option value="short">Short</option>
            </select>
          </label>
          <label className="block">
            <span className="text-sm font-medium text-slate-700">Start</span>
            <input
              className="mt-1 h-10 w-full rounded-md border border-stone-300 bg-white px-3 text-sm outline-none focus:border-teal-600"
              value={start}
              onChange={(event) => setStart(event.target.value)}
              type="datetime-local"
            />
          </label>
          <label className="block">
            <span className="text-sm font-medium text-slate-700">End</span>
            <input
              className="mt-1 h-10 w-full rounded-md border border-stone-300 bg-white px-3 text-sm outline-none focus:border-teal-600"
              value={end}
              onChange={(event) => setEnd(event.target.value)}
              type="datetime-local"
            />
          </label>
          <div>
            <span className="text-sm font-medium text-slate-700">Snapshot timeframe</span>
            <div className="mt-1">
              <TimeframeSelector value={timeframe} onChange={setTimeframe} includeAll />
            </div>
          </div>
        </div>
      </section>

      {positionsQuery.isLoading ? (
        <EmptyState title="Loading positions">Reading reconstructed positions.</EmptyState>
      ) : null}
      {positionsQuery.isError ? (
        <EmptyState title="Positions could not load">
          {(positionsQuery.error as Error).message}
        </EmptyState>
      ) : null}
      {positionsQuery.data ? <PositionsTable positions={positionsQuery.data} /> : null}
    </div>
  );
}
