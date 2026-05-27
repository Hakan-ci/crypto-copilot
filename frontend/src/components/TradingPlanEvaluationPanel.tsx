"use client";

import clsx from "clsx";
import { CheckCircle2, ClipboardCheck, HelpCircle, XCircle } from "lucide-react";

import type { TradingPlanEvaluation, TradingPlanEvaluationStatus } from "@/lib/types";

export function TradingPlanEvaluationPanel({
  evaluation
}: {
  evaluation: TradingPlanEvaluation | null;
}) {
  if (!evaluation || evaluation.items.length === 0) {
    return (
      <section className="rounded-md border border-dashed border-stone-300 bg-white px-4 py-6 text-sm text-slate-600">
        No enabled trading plan items are available for this position.
      </section>
    );
  }

  return (
    <section className="space-y-3">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h2 className="text-lg font-semibold text-slate-950">Trading plan</h2>
          <p className="mt-1 text-sm text-slate-600">
            Active plan evaluation for this reconstructed position.
          </p>
        </div>
        <div className="text-sm text-slate-700">
          <span className="font-semibold text-slate-950">{evaluation.score ?? "-"}</span>
          <span className="text-slate-500"> / 100</span>
        </div>
      </div>

      <div className="grid gap-3 md:grid-cols-4">
        <SummaryPill label="Passed" value={evaluation.passed_items_count} tone="positive" />
        <SummaryPill label="Failed" value={evaluation.failed_items_count} tone="negative" />
        <SummaryPill label="Unknown" value={evaluation.unknown_items_count} tone="neutral" />
        <SummaryPill label="Manual" value={evaluation.manual_items_count} tone="neutral" />
      </div>

      <div className="grid gap-3">
        {evaluation.items.map((item) => {
          const Icon = iconForStatus(item.status);
          return (
            <div
              key={item.item_id}
              className="rounded-md border border-stone-200 bg-white p-4 shadow-soft"
            >
              <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <Icon
                      className={clsx("h-4 w-4", classForStatus(item.status))}
                      aria-hidden="true"
                    />
                    <h3 className="text-sm font-semibold text-slate-950">{item.title}</h3>
                    {item.category ? (
                      <span className="rounded-md bg-stone-100 px-2 py-1 text-xs font-medium text-slate-600">
                        {item.category}
                      </span>
                    ) : null}
                  </div>
                  {item.description ? (
                    <p className="mt-2 text-sm text-slate-600">{item.description}</p>
                  ) : null}
                </div>
                <span
                  className={clsx(
                    "inline-flex h-7 items-center rounded-md px-2 text-xs font-semibold capitalize",
                    badgeClassForStatus(item.status)
                  )}
                >
                  {item.status}
                </span>
              </div>
              <p className="mt-3 text-sm text-slate-700">{item.message}</p>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function SummaryPill({
  label,
  tone,
  value
}: {
  label: string;
  tone: "positive" | "negative" | "neutral";
  value: number;
}) {
  return (
    <div
      className={clsx(
        "rounded-md border px-3 py-2",
        tone === "positive" && "border-emerald-200 bg-emerald-50 text-emerald-800",
        tone === "negative" && "border-red-200 bg-red-50 text-red-800",
        tone === "neutral" && "border-stone-200 bg-stone-50 text-slate-700"
      )}
    >
      <p className="text-xs font-medium uppercase tracking-[0.12em]">{label}</p>
      <p className="mt-1 text-lg font-semibold">{value}</p>
    </div>
  );
}

function iconForStatus(status: TradingPlanEvaluationStatus) {
  if (status === "passed") {
    return CheckCircle2;
  }
  if (status === "failed") {
    return XCircle;
  }
  if (status === "manual") {
    return ClipboardCheck;
  }
  return HelpCircle;
}

function classForStatus(status: TradingPlanEvaluationStatus) {
  if (status === "passed") {
    return "text-emerald-600";
  }
  if (status === "failed") {
    return "text-red-600";
  }
  return "text-slate-500";
}

function badgeClassForStatus(status: TradingPlanEvaluationStatus) {
  if (status === "passed") {
    return "bg-emerald-50 text-emerald-700";
  }
  if (status === "failed") {
    return "bg-red-50 text-red-700";
  }
  if (status === "manual") {
    return "bg-teal-50 text-teal-700";
  }
  return "bg-stone-100 text-slate-700";
}
