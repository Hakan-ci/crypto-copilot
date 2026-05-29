"use client";

import { ShieldCheck } from "lucide-react";

import { formatDecimal } from "@/lib/format";
import type { PositionTradeMetadata } from "@/lib/types";

export function StopLossMetadataPanel({
  metadata
}: {
  metadata: PositionTradeMetadata | null;
}) {
  const stopLoss = metadata?.planned_stop_loss_price ?? null;

  return (
    <section className="rounded-md border border-stone-200 bg-white p-4 shadow-soft">
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <ShieldCheck className="h-5 w-5 text-teal-700" aria-hidden="true" />
            <h2 className="text-lg font-semibold text-slate-950">Planned stop-loss</h2>
          </div>
          <p className="mt-1 text-sm text-slate-600">
            Synced from MEXC read-only stop order data.
          </p>
        </div>
      </div>

      <div className="mt-4 rounded-md border border-stone-200 bg-stone-50 px-3 py-2">
        <p className="text-xs font-medium uppercase tracking-[0.12em] text-slate-500">
          Stop price
        </p>
        <p className="mt-1 text-lg font-semibold text-slate-950">
          {stopLoss ? formatDecimal(stopLoss, 6) : "No stop-loss found in MEXC data"}
        </p>
      </div>
    </section>
  );
}
