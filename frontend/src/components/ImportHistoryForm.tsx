"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Download } from "lucide-react";
import { FormEvent, useState } from "react";

import { importOrderDealsAndReconstruct } from "@/lib/api";

function dateToMilliseconds(value: string) {
  if (!value) {
    return undefined;
  }
  const timestamp = new Date(value).getTime();
  return Number.isFinite(timestamp) ? timestamp : undefined;
}

export function ImportHistoryForm({ userId }: { userId: string }) {
  const [symbol, setSymbol] = useState("BTC_USDT");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: () =>
      importOrderDealsAndReconstruct({
        user_id: userId,
        symbol: symbol.trim().toUpperCase(),
        start_time_ms: dateToMilliseconds(start),
        end_time_ms: dateToMilliseconds(end)
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["dashboard", userId] });
      void queryClient.invalidateQueries({ queryKey: ["positions", userId] });
    }
  });

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    mutation.mutate();
  }

  return (
    <form className="max-w-3xl space-y-4" onSubmit={handleSubmit}>
      <div className="grid gap-4 md:grid-cols-3">
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
          <span className="text-sm font-medium text-slate-700">Start date</span>
          <input
            className="mt-1 h-10 w-full rounded-md border border-stone-300 bg-white px-3 text-sm outline-none focus:border-teal-600"
            value={start}
            onChange={(event) => setStart(event.target.value)}
            type="datetime-local"
          />
        </label>
        <label className="block">
          <span className="text-sm font-medium text-slate-700">End date</span>
          <input
            className="mt-1 h-10 w-full rounded-md border border-stone-300 bg-white px-3 text-sm outline-none focus:border-teal-600"
            value={end}
            onChange={(event) => setEnd(event.target.value)}
            type="datetime-local"
          />
        </label>
      </div>
      <button
        className="inline-flex h-10 items-center justify-center gap-2 rounded-md bg-slate-900 px-4 text-sm font-medium text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-400"
        type="submit"
        disabled={!userId || !symbol.trim() || mutation.isPending}
      >
        <Download className="h-4 w-4" aria-hidden="true" />
        {mutation.isPending ? "Preparing..." : "Import and reconstruct"}
      </button>
      {mutation.isError ? (
        <p className="text-sm text-red-700">{(mutation.error as Error).message}</p>
      ) : null}
      {mutation.data ? (
        <div className="space-y-2 rounded-md border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-900">
          <p>
            Imported {mutation.data.imported} rows for {mutation.data.symbol}. Skipped{" "}
            {mutation.data.skipped_duplicates} duplicates.
          </p>
          <p>
            Reconstructed {mutation.data.positions_created} positions:{" "}
            {mutation.data.closed_positions} closed / {mutation.data.open_positions} open.
          </p>
          {mutation.data.warnings.length ? (
            <p className="text-amber-900">{mutation.data.warnings.join(" ")}</p>
          ) : null}
        </div>
      ) : null}
    </form>
  );
}
