import { AlertTriangle } from "lucide-react";

import type { IndicatorSnapshot, Position } from "@/lib/types";

export function RiskWarnings({
  position,
  snapshots
}: {
  position: Position;
  snapshots: IndicatorSnapshot[];
}) {
  const warnings: string[] = [];

  snapshots.forEach((snapshot) => {
    const rsi = snapshot.rsi_14 === null ? Number.NaN : Number(snapshot.rsi_14);
    if (Number.isFinite(rsi) && rsi > 70) {
      warnings.push(`${snapshot.timeframe}: RSI was overbought at entry.`);
    }
    if (Number.isFinite(rsi) && rsi < 30) {
      warnings.push(`${snapshot.timeframe}: RSI was oversold at entry.`);
    }
    if (
      position.direction === "long" &&
      snapshot.supertrend_direction === "bearish"
    ) {
      warnings.push(`${snapshot.timeframe}: Long trade was against Supertrend.`);
    }
    if (
      position.direction === "short" &&
      snapshot.supertrend_direction === "bullish"
    ) {
      warnings.push(`${snapshot.timeframe}: Short trade was against Supertrend.`);
    }
  });

  if (warnings.length === 0) {
    return (
      <div className="rounded-md border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
        No obvious indicator warnings were found in the stored snapshots.
      </div>
    );
  }

  return (
    <div className="rounded-md border border-amber-200 bg-amber-50 px-4 py-3">
      <div className="flex items-center gap-2 text-sm font-semibold text-amber-900">
        <AlertTriangle className="h-4 w-4" aria-hidden="true" />
        Review notes
      </div>
      <ul className="mt-2 space-y-1 text-sm text-amber-900">
        {warnings.map((warning) => (
          <li key={warning}>{warning}</li>
        ))}
      </ul>
    </div>
  );
}
