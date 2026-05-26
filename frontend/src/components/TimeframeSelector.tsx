"use client";

import clsx from "clsx";

import { TIMEFRAMES } from "@/lib/timeframes";
import type { Timeframe } from "@/lib/types";

export function TimeframeSelector({
  value,
  onChange,
  includeAll = false
}: {
  value: Timeframe | "all";
  onChange: (value: Timeframe | "all") => void;
  includeAll?: boolean;
}) {
  const options = includeAll ? [{ label: "All", value: "all" as const }, ...TIMEFRAMES] : TIMEFRAMES;

  return (
    <div className="inline-flex rounded-md border border-stone-300 bg-white p-1">
      {options.map((option) => (
        <button
          key={option.value}
          className={clsx(
            "h-8 rounded px-3 text-sm font-medium transition",
            value === option.value
              ? "bg-slate-900 text-white"
              : "text-slate-600 hover:bg-stone-100 hover:text-slate-950"
          )}
          type="button"
          onClick={() => onChange(option.value)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
