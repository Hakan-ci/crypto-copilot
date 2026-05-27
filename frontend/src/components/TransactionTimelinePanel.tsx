import { formatCurrency, formatDateTime, formatDecimal } from "@/lib/format";
import type { PositionTransaction } from "@/lib/types";

export function TransactionTimelinePanel({
  source,
  transactions
}: {
  source: "linked" | "inferred" | "unavailable";
  transactions: PositionTransaction[];
}) {
  if (transactions.length === 0) {
    return (
      <section className="rounded-md border border-dashed border-stone-300 bg-white px-4 py-6 text-sm text-slate-600">
        No transaction timeline is available for this position.
      </section>
    );
  }

  return (
    <section className="space-y-3">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h2 className="text-lg font-semibold text-slate-950">Transaction timeline</h2>
          <p className="mt-1 text-sm text-slate-600">
            Imported fills ordered by stored exchange transaction time.
          </p>
        </div>
        <span className="inline-flex h-7 items-center rounded-md bg-stone-100 px-2 text-xs font-semibold capitalize text-slate-700">
          {source}
        </span>
      </div>
      {source === "inferred" ? (
        <p className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
          This timeline was inferred from raw fills by symbol and time range.
        </p>
      ) : null}
      <div className="overflow-hidden rounded-md border border-stone-200 bg-white shadow-soft">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-stone-200 text-sm">
            <thead className="bg-stone-50 text-left text-xs font-semibold uppercase tracking-[0.12em] text-slate-500">
              <tr>
                <th className="px-4 py-3">Time</th>
                <th className="px-4 py-3">Side</th>
                <th className="px-4 py-3">Volume</th>
                <th className="px-4 py-3">Price</th>
                <th className="px-4 py-3">Fee</th>
                <th className="px-4 py-3">PnL</th>
                <th className="px-4 py-3">Deal</th>
                <th className="px-4 py-3">Order</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-100">
              {transactions.map((transaction) => (
                <tr key={`${transaction.mexc_deal_id}-${transaction.timestamp_ms}`}>
                  <td className="whitespace-nowrap px-4 py-3 text-slate-700">
                    {formatDateTime(transaction.timestamp)}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 font-medium text-slate-950">
                    {transaction.side_label.replace(/_/g, " ")}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-slate-700">
                    {formatDecimal(transaction.vol, 4)}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-slate-700">
                    {formatDecimal(transaction.price, 4)}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-slate-700">
                    {formatCurrency(transaction.fee)}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-slate-700">
                    {formatCurrency(transaction.profit)}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 font-mono text-xs text-slate-600">
                    {transaction.mexc_deal_id}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 font-mono text-xs text-slate-600">
                    {transaction.order_id}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}
