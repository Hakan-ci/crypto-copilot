"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, Plus, Save, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import { EmptyState } from "@/components/EmptyState";
import { getTradingPlan, putTradingPlan } from "@/lib/api";
import { useDevelopmentUserId } from "@/lib/storage";
import { TIMEFRAMES } from "@/lib/timeframes";
import type {
  TradingPlanItem,
  TradingPlanItemInput,
  TradingPlanRuleType
} from "@/lib/types";

const RULE_OPTIONS: Array<{ value: TradingPlanRuleType; label: string }> = [
  { value: "manual_check", label: "Manual check" },
  { value: "allowed_symbols", label: "Allowed symbols" },
  { value: "required_timeframes", label: "Required timeframes" },
  { value: "max_trades_per_day", label: "Max trades per day" },
  { value: "max_leverage", label: "Max leverage" },
  { value: "max_risk_per_trade", label: "Max risk per trade" },
  { value: "min_risk_reward", label: "Minimum risk/reward" }
];

type DraftItem = Omit<TradingPlanItemInput, "id"> & { id?: string | null };

export function TradingPlanForm() {
  const { userId, isReady } = useDevelopmentUserId();
  const queryClient = useQueryClient();
  const [items, setItems] = useState<DraftItem[]>([]);
  const [saved, setSaved] = useState(false);

  const planQuery = useQuery({
    queryKey: ["trading-plan", userId],
    queryFn: () => getTradingPlan(userId),
    enabled: Boolean(userId)
  });

  useEffect(() => {
    if (planQuery.data) {
      setItems(planQuery.data.items.map(itemToDraft));
      setSaved(false);
    }
  }, [planQuery.data]);

  const normalizedItems = useMemo(
    () => items.map((item, index) => ({ ...item, sort_order: index })),
    [items]
  );

  const saveMutation = useMutation({
    mutationFn: () => putTradingPlan(userId, { items: normalizedItems }),
    onSuccess: (plan) => {
      setItems(plan.items.map(itemToDraft));
      setSaved(true);
      void queryClient.invalidateQueries({ queryKey: ["positions", userId] });
      void queryClient.invalidateQueries({ queryKey: ["position-detail"] });
      void queryClient.invalidateQueries({ queryKey: ["trading-plan", userId] });
    }
  });

  if (!isReady) {
    return <EmptyState title="Loading workspace">Preparing your local workspace.</EmptyState>;
  }

  if (!userId) {
    return (
      <EmptyState title="Add a development user ID">
        Paste a backend user UUID in the header before editing the trading plan.
      </EmptyState>
    );
  }

  if (planQuery.isLoading) {
    return <EmptyState title="Loading trading plan">Reading saved plan items.</EmptyState>;
  }

  if (planQuery.isError) {
    return (
      <EmptyState title="Trading plan could not load">
        {(planQuery.error as Error).message}
      </EmptyState>
    );
  }

  function updateItem(index: number, nextItem: DraftItem) {
    setItems((current) =>
      current.map((item, itemIndex) => (itemIndex === index ? nextItem : item))
    );
    setSaved(false);
  }

  function updateConfig(index: number, key: string, value: unknown) {
    const item = items[index];
    updateItem(index, {
      ...item,
      config: {
        ...item.config,
        [key]: value
      }
    });
  }

  function addItem() {
    setItems((current) => [
      ...current,
      {
        sort_order: current.length,
        title: "New plan item",
        description: null,
        category: null,
        rule_type: "manual_check",
        enabled: true,
        config: {}
      }
    ]);
    setSaved(false);
  }

  function removeItem(index: number) {
    setItems((current) => current.filter((_, itemIndex) => itemIndex !== index));
    setSaved(false);
  }

  function moveItem(index: number, direction: -1 | 1) {
    const targetIndex = index + direction;
    if (targetIndex < 0 || targetIndex >= items.length) {
      return;
    }
    setItems((current) => {
      const nextItems = [...current];
      const [movedItem] = nextItems.splice(index, 1);
      nextItems.splice(targetIndex, 0, movedItem);
      return nextItems;
    });
    setSaved(false);
  }

  return (
    <form
      className="space-y-4"
      onSubmit={(event) => {
        event.preventDefault();
        saveMutation.mutate();
      }}
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <button
          className="inline-flex h-10 items-center justify-center gap-2 rounded-md border border-stone-300 bg-white px-4 text-sm font-medium text-slate-800 hover:bg-stone-100"
          type="button"
          onClick={addItem}
        >
          <Plus className="h-4 w-4" aria-hidden="true" />
          Add item
        </button>
        <button
          className="inline-flex h-10 items-center justify-center gap-2 rounded-md bg-slate-900 px-4 text-sm font-medium text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-400"
          type="submit"
          disabled={saveMutation.isPending}
        >
          <Save className="h-4 w-4" aria-hidden="true" />
          {saveMutation.isPending ? "Saving..." : "Save plan"}
        </button>
      </div>

      {items.length === 0 ? (
        <EmptyState title="No plan items yet">Add checklist and rule items to start.</EmptyState>
      ) : (
        <div className="grid gap-4">
          {items.map((item, index) => (
            <div
              key={item.id ?? `${item.rule_type}-${index}`}
              className="rounded-md border border-stone-200 bg-white p-4 shadow-soft"
            >
              <div className="flex flex-col gap-3 xl:flex-row xl:items-start xl:justify-between">
                <div className="grid flex-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
                  <label className="block xl:col-span-2">
                    <span className="text-sm font-medium text-slate-700">Title</span>
                    <input
                      className="mt-1 h-10 w-full rounded-md border border-stone-300 bg-white px-3 text-sm outline-none focus:border-teal-600"
                      value={item.title}
                      onChange={(event) =>
                        updateItem(index, { ...item, title: event.target.value })
                      }
                    />
                  </label>
                  <label className="block">
                    <span className="text-sm font-medium text-slate-700">Category</span>
                    <input
                      className="mt-1 h-10 w-full rounded-md border border-stone-300 bg-white px-3 text-sm outline-none focus:border-teal-600"
                      value={item.category ?? ""}
                      onChange={(event) =>
                        updateItem(index, {
                          ...item,
                          category: event.target.value || null
                        })
                      }
                      placeholder="Risk, Setup, Exit"
                    />
                  </label>
                  <label className="block">
                    <span className="text-sm font-medium text-slate-700">Rule type</span>
                    <select
                      className="mt-1 h-10 w-full rounded-md border border-stone-300 bg-white px-3 text-sm outline-none focus:border-teal-600"
                      value={item.rule_type}
                      onChange={(event) => {
                        const ruleType = event.target.value as TradingPlanRuleType;
                        updateItem(index, {
                          ...item,
                          rule_type: ruleType,
                          config: defaultConfigForRule(ruleType)
                        });
                      }}
                    >
                      {RULE_OPTIONS.map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
                <div className="flex items-center gap-2">
                  <label className="inline-flex h-10 items-center gap-2 rounded-md border border-stone-300 bg-white px-3 text-sm font-medium text-slate-700">
                    <input
                      checked={item.enabled}
                      onChange={(event) =>
                        updateItem(index, { ...item, enabled: event.target.checked })
                      }
                      type="checkbox"
                    />
                    Enabled
                  </label>
                  <IconButton
                    label="Move up"
                    disabled={index === 0}
                    onClick={() => moveItem(index, -1)}
                  >
                    <ArrowUp className="h-4 w-4" aria-hidden="true" />
                  </IconButton>
                  <IconButton
                    label="Move down"
                    disabled={index === items.length - 1}
                    onClick={() => moveItem(index, 1)}
                  >
                    <ArrowDown className="h-4 w-4" aria-hidden="true" />
                  </IconButton>
                  <IconButton label="Delete item" onClick={() => removeItem(index)}>
                    <Trash2 className="h-4 w-4" aria-hidden="true" />
                  </IconButton>
                </div>
              </div>

              <label className="mt-3 block">
                <span className="text-sm font-medium text-slate-700">Description</span>
                <textarea
                  className="mt-1 min-h-20 w-full rounded-md border border-stone-300 bg-white px-3 py-2 text-sm outline-none focus:border-teal-600"
                  value={item.description ?? ""}
                  onChange={(event) =>
                    updateItem(index, {
                      ...item,
                      description: event.target.value || null
                    })
                  }
                />
              </label>

              <RuleConfigFields
                item={item}
                onChange={(key, value) => updateConfig(index, key, value)}
              />
            </div>
          ))}
        </div>
      )}

      {saveMutation.isError ? (
        <p className="text-sm text-red-700">{(saveMutation.error as Error).message}</p>
      ) : null}
      {saved ? <p className="text-sm text-emerald-700">Trading plan saved.</p> : null}
    </form>
  );
}

function RuleConfigFields({
  item,
  onChange
}: {
  item: DraftItem;
  onChange: (key: string, value: unknown) => void;
}) {
  if (item.rule_type === "manual_check") {
    return null;
  }

  if (item.rule_type === "allowed_symbols") {
    return (
      <label className="mt-3 block">
        <span className="text-sm font-medium text-slate-700">Symbols</span>
        <input
          className="mt-1 h-10 w-full rounded-md border border-stone-300 bg-white px-3 text-sm uppercase outline-none focus:border-teal-600"
          value={stringArray(item.config.symbols).join(", ")}
          onChange={(event) =>
            onChange(
              "symbols",
              event.target.value
                .split(",")
                .map((value) => value.trim().toUpperCase())
                .filter(Boolean)
            )
          }
          placeholder="BTC_USDT, ETH_USDT"
        />
      </label>
    );
  }

  if (item.rule_type === "required_timeframes") {
    const selectedTimeframes = new Set(stringArray(item.config.timeframes));
    return (
      <fieldset className="mt-3">
        <legend className="text-sm font-medium text-slate-700">Required snapshots</legend>
        <div className="mt-2 flex flex-wrap gap-2">
          {TIMEFRAMES.map((timeframe) => (
            <label
              key={timeframe.value}
              className="inline-flex h-9 items-center gap-2 rounded-md border border-stone-300 bg-white px-3 text-sm text-slate-700"
            >
              <input
                checked={selectedTimeframes.has(timeframe.value)}
                onChange={(event) => {
                  const nextTimeframes = new Set(selectedTimeframes);
                  if (event.target.checked) {
                    nextTimeframes.add(timeframe.value);
                  } else {
                    nextTimeframes.delete(timeframe.value);
                  }
                  onChange("timeframes", Array.from(nextTimeframes));
                }}
                type="checkbox"
              />
              {timeframe.label}
            </label>
          ))}
        </div>
      </fieldset>
    );
  }

  return (
    <label className="mt-3 block max-w-xs">
      <span className="text-sm font-medium text-slate-700">{limitLabel(item.rule_type)}</span>
      <input
        className="mt-1 h-10 w-full rounded-md border border-stone-300 bg-white px-3 text-sm outline-none focus:border-teal-600"
        min="0"
        step="any"
        type="number"
        value={String(item.config.limit ?? "")}
        onChange={(event) => onChange("limit", event.target.value)}
      />
    </label>
  );
}

function IconButton({
  children,
  disabled,
  label,
  onClick
}: {
  children: ReactNode;
  disabled?: boolean;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      aria-label={label}
      className="inline-flex h-10 w-10 items-center justify-center rounded-md border border-stone-300 bg-white text-slate-700 hover:bg-stone-100 disabled:cursor-not-allowed disabled:text-slate-300"
      disabled={disabled}
      onClick={onClick}
      title={label}
      type="button"
    >
      {children}
    </button>
  );
}

function itemToDraft(item: TradingPlanItem): DraftItem {
  return {
    id: item.id,
    sort_order: item.sort_order,
    title: item.title,
    description: item.description,
    category: item.category,
    rule_type: item.rule_type,
    enabled: item.enabled,
    config: item.config ?? {}
  };
}

function defaultConfigForRule(ruleType: TradingPlanRuleType): Record<string, unknown> {
  if (ruleType === "allowed_symbols") {
    return { symbols: [] };
  }
  if (ruleType === "required_timeframes") {
    return { timeframes: TIMEFRAMES.map((timeframe) => timeframe.value) };
  }
  if (ruleType === "manual_check") {
    return {};
  }
  return { limit: "" };
}

function stringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.map((item) => String(item)) : [];
}

function limitLabel(ruleType: TradingPlanRuleType) {
  if (ruleType === "max_trades_per_day") {
    return "Daily trade limit";
  }
  if (ruleType === "max_leverage") {
    return "Leverage limit";
  }
  if (ruleType === "max_risk_per_trade") {
    return "Maximum risk";
  }
  return "Minimum risk/reward";
}
