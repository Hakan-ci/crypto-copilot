import { formatDateTime, formatDecimal } from "@/lib/format";
import { timeframeLabel } from "@/lib/timeframes";
import type { IndicatorSnapshot } from "@/lib/types";

import { IndicatorBadges } from "@/components/IndicatorBadges";

export function IndicatorSnapshotPanel({ snapshot }: { snapshot: IndicatorSnapshot }) {
  return (
    <section className="rounded-md border border-stone-200 bg-white p-4 shadow-soft">
      <div className="mb-4 flex flex-col gap-1 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h3 className="text-base font-semibold text-slate-950">
            {timeframeLabel(snapshot.timeframe)} snapshot
          </h3>
          <p className="text-sm text-slate-600">
            Candle at or before entry: {formatDateTime(snapshot.timestamp)}
          </p>
        </div>
        <p className="text-sm font-medium text-slate-700">Price {formatDecimal(snapshot.price, 4)}</p>
      </div>
      <IndicatorBadges snapshot={snapshot} />
      <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-3">
        <div>
          <dt className="text-slate-500">ATR 14</dt>
          <dd className="font-medium text-slate-950">{formatDecimal(snapshot.atr_14, 4)}</dd>
        </div>
        <div>
          <dt className="text-slate-500">Relative volume</dt>
          <dd className="font-medium text-slate-950">{formatDecimal(snapshot.volume_relative, 3)}</dd>
        </div>
        <div>
          <dt className="text-slate-500">Trend label</dt>
          <dd className="font-medium capitalize text-slate-950">{snapshot.trend_label ?? "-"}</dd>
        </div>
      </dl>
    </section>
  );
}
