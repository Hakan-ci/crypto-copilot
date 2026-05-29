"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, Plus, Save, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import { EmptyState } from "@/components/EmptyState";
import { getTradingPlan, putTradingPlan } from "@/lib/api";
import { useDevelopmentUserId } from "@/lib/storage";
import type { TradingPlanItem, TradingPlanItemInput } from "@/lib/types";

type DraftItem = Pick<TradingPlanItemInput, "sort_order" | "title" | "description"> & {
  id?: string | null;
};

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

  const normalizedItems = useMemo<TradingPlanItemInput[]>(
    () =>
      items.map((item, index) => ({
        id: item.id,
        sort_order: index,
        title: item.title,
        description: item.description,
        category: null,
        rule_type: "manual_check",
        enabled: true,
        config: {}
      })),
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

  function addItem() {
    setItems((current) => [
      ...current,
      {
        sort_order: current.length,
        title: "New system rule",
        description: null
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
          Add rule
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
        <EmptyState title="No system rules yet">Add system rules to start.</EmptyState>
      ) : (
        <div className="grid gap-4">
          {items.map((item, index) => (
            <div
              key={item.id ?? `system-rule-${index}`}
              className="rounded-md border border-stone-200 bg-white p-4 shadow-soft"
            >
              <div className="flex flex-col gap-3 xl:flex-row xl:items-start xl:justify-between">
                <div className="flex-1">
                  <label className="block">
                    <span className="text-sm font-medium text-slate-700">Title</span>
                    <input
                      className="mt-1 h-10 w-full rounded-md border border-stone-300 bg-white px-3 text-sm outline-none focus:border-teal-600"
                      value={item.title}
                      onChange={(event) =>
                        updateItem(index, { ...item, title: event.target.value })
                      }
                    />
                  </label>
                </div>
                <div className="flex items-center gap-2">
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
    description: item.description
  };
}
