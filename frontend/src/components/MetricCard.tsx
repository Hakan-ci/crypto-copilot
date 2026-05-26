import clsx from "clsx";
import { LucideIcon } from "lucide-react";

export function MetricCard({
  label,
  value,
  helper,
  icon: Icon,
  tone = "neutral"
}: {
  label: string;
  value: string;
  helper?: string;
  icon?: LucideIcon;
  tone?: "neutral" | "positive" | "negative" | "warning";
}) {
  return (
    <div className="rounded-md border border-stone-200 bg-white p-4 shadow-soft">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-medium uppercase tracking-[0.12em] text-slate-500">{label}</p>
          <p
            className={clsx(
              "mt-2 text-2xl font-semibold",
              tone === "positive" && "text-emerald-700",
              tone === "negative" && "text-red-700",
              tone === "warning" && "text-amber-700",
              tone === "neutral" && "text-slate-950"
            )}
          >
            {value}
          </p>
        </div>
        {Icon ? (
          <span className="inline-flex h-9 w-9 items-center justify-center rounded-md bg-stone-100 text-slate-700">
            <Icon className="h-4 w-4" aria-hidden="true" />
          </span>
        ) : null}
      </div>
      {helper ? <p className="mt-3 text-sm text-slate-600">{helper}</p> : null}
    </div>
  );
}
