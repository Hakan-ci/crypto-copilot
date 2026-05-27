import Link from "next/link";

import { classForPnl, formatCurrency, formatDateTime, formatDecimal } from "@/lib/format";
import type { Position } from "@/lib/types";

export function PositionsTable({ positions }: { positions: Position[] }) {
  if (positions.length === 0) {
    return (
      <div className="rounded-md border border-dashed border-stone-300 bg-white px-4 py-8 text-center text-sm text-slate-600">
        No reconstructed positions match these filters yet.
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-md border border-stone-200 bg-white shadow-soft">
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-stone-200 text-sm">
          <thead className="bg-stone-50 text-left text-xs font-semibold uppercase tracking-[0.12em] text-slate-500">
            <tr>
              <th className="px-4 py-3">Symbol</th>
              <th className="px-4 py-3">Direction</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Opened</th>
              <th className="px-4 py-3">Entry</th>
              <th className="px-4 py-3">Exit</th>
              <th className="px-4 py-3">Net PnL</th>
              <th className="px-4 py-3">Plan</th>
              <th className="px-4 py-3">Review</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-stone-100">
            {positions.map((position) => (
              <tr key={position.id} className="hover:bg-stone-50">
                <td className="whitespace-nowrap px-4 py-3 font-medium text-slate-950">
                  {position.symbol}
                </td>
                <td className="whitespace-nowrap px-4 py-3 capitalize text-slate-700">
                  {position.direction}
                </td>
                <td className="whitespace-nowrap px-4 py-3 capitalize text-slate-700">
                  {position.status}
                </td>
                <td className="whitespace-nowrap px-4 py-3 text-slate-600">
                  {formatDateTime(position.opened_at)}
                </td>
                <td className="whitespace-nowrap px-4 py-3 text-slate-700">
                  {formatDecimal(position.avg_entry_price, 4)}
                </td>
                <td className="whitespace-nowrap px-4 py-3 text-slate-700">
                  {formatDecimal(position.avg_exit_price, 4)}
                </td>
                <td
                  className={`whitespace-nowrap px-4 py-3 font-semibold ${classForPnl(
                    position.net_pnl ?? position.realized_pnl
                  )}`}
                >
                  {formatCurrency(position.net_pnl ?? position.realized_pnl)}
                </td>
                <td className="whitespace-nowrap px-4 py-3">
                  <PlanBadge position={position} />
                </td>
                <td className="whitespace-nowrap px-4 py-3">
                  <Link
                    href={`/positions/${position.id}`}
                    className="rounded-md border border-stone-300 px-3 py-1.5 text-sm font-medium text-slate-800 hover:bg-stone-100"
                  >
                    Open
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function PlanBadge({ position }: { position: Position }) {
  const failedCount = position.plan_failed_items_count ?? 0;
  const unknownCount = position.plan_unknown_items_count ?? 0;
  const score = position.plan_score;

  if (score === null || score === undefined) {
    if (unknownCount > 0) {
      return (
        <span className="inline-flex rounded-md border border-stone-200 bg-stone-50 px-2 py-1 text-xs font-semibold text-slate-700">
          {unknownCount} unknown
        </span>
      );
    }
    return <span className="text-sm text-slate-500">-</span>;
  }

  const tone =
    failedCount > 0
      ? "border-red-200 bg-red-50 text-red-700"
      : unknownCount > 0
        ? "border-amber-200 bg-amber-50 text-amber-800"
        : "border-emerald-200 bg-emerald-50 text-emerald-700";

  return (
    <span className={`inline-flex rounded-md border px-2 py-1 text-xs font-semibold ${tone}`}>
      {score}/100
      {failedCount > 0 ? `, ${failedCount} failed` : ""}
      {failedCount === 0 && unknownCount > 0 ? `, ${unknownCount} unknown` : ""}
    </span>
  );
}
