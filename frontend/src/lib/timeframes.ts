import type { Timeframe, TimeframeLabel } from "@/lib/types";

export const TIMEFRAMES: Array<{ label: TimeframeLabel; value: Timeframe }> = [
  { label: "1H", value: "Min60" },
  { label: "4H", value: "Hour4" },
  { label: "1D", value: "Day1" }
];

export function timeframeLabel(value: Timeframe): TimeframeLabel {
  return TIMEFRAMES.find((timeframe) => timeframe.value === value)?.label ?? "1H";
}
