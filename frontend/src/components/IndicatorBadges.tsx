import clsx from "clsx";

import { formatDecimal } from "@/lib/format";
import type { IndicatorSnapshot } from "@/lib/types";

export function IndicatorBadges({ snapshot }: { snapshot: IndicatorSnapshot }) {
  const macdLabel =
    snapshot.macd && snapshot.macd_signal
      ? `${formatDecimal(snapshot.macd, 4)} / ${formatDecimal(snapshot.macd_signal, 4)}`
      : "-";

  const items = [
    {
      label: "RSI",
      value: formatDecimal(snapshot.rsi_14, 2),
      tone:
        Number(snapshot.rsi_14 ?? 50) > 70
          ? "warning"
          : Number(snapshot.rsi_14 ?? 50) < 30
            ? "positive"
            : "neutral"
    },
    {
      label: "Stoch RSI",
      value: `${formatDecimal(snapshot.stoch_rsi_k, 2)} / ${formatDecimal(snapshot.stoch_rsi_d, 2)}`,
      tone: "neutral"
    },
    { label: "MACD", value: macdLabel, tone: "neutral" },
    {
      label: "Supertrend",
      value: snapshot.supertrend_direction ?? "-",
      tone: snapshot.supertrend_direction === "bullish" ? "positive" : "negative"
    }
  ];

  return (
    <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
      {items.map((item) => (
        <div
          key={item.label}
          className={clsx(
            "rounded-md border px-3 py-2",
            item.tone === "positive" && "border-emerald-200 bg-emerald-50 text-emerald-800",
            item.tone === "negative" && "border-red-200 bg-red-50 text-red-800",
            item.tone === "warning" && "border-amber-200 bg-amber-50 text-amber-800",
            item.tone === "neutral" && "border-stone-200 bg-stone-50 text-slate-800"
          )}
        >
          <p className="text-xs font-medium uppercase tracking-[0.12em] opacity-75">{item.label}</p>
          <p className="mt-1 text-sm font-semibold capitalize">{item.value}</p>
        </div>
      ))}
    </div>
  );
}
