"use client";

import { Save } from "lucide-react";
import { FormEvent, useEffect, useState } from "react";

import { loadTradingPlan, saveTradingPlan } from "@/lib/storage";
import type { UserTradingRules } from "@/lib/types";

export function TradingPlanForm() {
  const [plan, setPlan] = useState<UserTradingRules>({});
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    setPlan(loadTradingPlan());
  }, []);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    saveTradingPlan(plan);
    setSaved(true);
  }

  function update<K extends keyof UserTradingRules>(key: K, value: UserTradingRules[K]) {
    setPlan((current) => ({ ...current, [key]: value }));
    setSaved(false);
  }

  return (
    <form className="max-w-3xl space-y-4" onSubmit={handleSubmit}>
      <div className="grid gap-4 md:grid-cols-2">
        <label className="block">
          <span className="text-sm font-medium text-slate-700">Max risk per trade</span>
          <input
            className="mt-1 h-10 w-full rounded-md border border-stone-300 bg-white px-3 text-sm outline-none focus:border-teal-600"
            value={plan.max_risk_per_trade ?? ""}
            onChange={(event) => update("max_risk_per_trade", event.target.value || null)}
            placeholder="Example: 0.01 for 1%"
          />
        </label>
        <label className="block">
          <span className="text-sm font-medium text-slate-700">Minimum risk/reward</span>
          <input
            className="mt-1 h-10 w-full rounded-md border border-stone-300 bg-white px-3 text-sm outline-none focus:border-teal-600"
            value={plan.min_risk_reward ?? ""}
            onChange={(event) => update("min_risk_reward", event.target.value || null)}
            placeholder="Example: 2"
          />
        </label>
        <label className="block">
          <span className="text-sm font-medium text-slate-700">Allowed symbols</span>
          <input
            className="mt-1 h-10 w-full rounded-md border border-stone-300 bg-white px-3 text-sm outline-none focus:border-teal-600"
            value={plan.allowed_symbols?.join(", ") ?? ""}
            onChange={(event) =>
              update(
                "allowed_symbols",
                event.target.value
                  .split(",")
                  .map((item) => item.trim().toUpperCase())
                  .filter(Boolean)
              )
            }
            placeholder="BTC_USDT, ETH_USDT"
          />
        </label>
        <label className="block">
          <span className="text-sm font-medium text-slate-700">Max trades per day</span>
          <input
            className="mt-1 h-10 w-full rounded-md border border-stone-300 bg-white px-3 text-sm outline-none focus:border-teal-600"
            value={plan.max_trades_per_day ?? ""}
            onChange={(event) =>
              update(
                "max_trades_per_day",
                event.target.value ? Number(event.target.value) : null
              )
            }
            type="number"
            min="0"
          />
        </label>
      </div>
      <label className="block">
        <span className="text-sm font-medium text-slate-700">Notes</span>
        <textarea
          className="mt-1 min-h-32 w-full rounded-md border border-stone-300 bg-white px-3 py-2 text-sm outline-none focus:border-teal-600"
          value={plan.notes ?? ""}
          onChange={(event) => update("notes", event.target.value || null)}
          placeholder="Write your checklist, setup rules, and review reminders."
        />
      </label>
      <button
        className="inline-flex h-10 items-center justify-center gap-2 rounded-md bg-slate-900 px-4 text-sm font-medium text-white hover:bg-slate-800"
        type="submit"
      >
        <Save className="h-4 w-4" aria-hidden="true" />
        Save trading plan
      </button>
      {saved ? <p className="text-sm text-emerald-700">Trading plan saved locally.</p> : null}
    </form>
  );
}
