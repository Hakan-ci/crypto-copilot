"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, Check, Plus, RefreshCw, Trash2 } from "lucide-react";
import type { ReactNode } from "react";
import { useEffect, useMemo, useState } from "react";

import { getCryptoBasket, putCryptoBasket, syncCryptoBasket } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import type { CryptoBasketItem, CryptoBasketItemInput, CryptoBasketSyncRun } from "@/lib/types";

type DraftItem = CryptoBasketItemInput;

export function CryptoBasketForm({ userId }: { userId: string }) {
  const [items, setItems] = useState<DraftItem[]>([]);
  const [newSymbol, setNewSymbol] = useState("BTC_USDT");
  const queryClient = useQueryClient();

  const basketQuery = useQuery({
    queryKey: ["crypto-basket", userId],
    queryFn: () => getCryptoBasket(userId),
    enabled: Boolean(userId)
  });

  useEffect(() => {
    if (!basketQuery.data) {
      return;
    }
    setItems(
      basketQuery.data.items.map((item) => ({
        id: item.id,
        sort_order: item.sort_order,
        symbol: item.symbol,
        enabled: item.enabled
      }))
    );
  }, [basketQuery.data]);

  const statusBySymbol = useMemo(() => {
    const statuses = new Map<string, CryptoBasketItem>();
    basketQuery.data?.items.forEach((item) => statuses.set(item.symbol, item));
    return statuses;
  }, [basketQuery.data]);

  const saveMutation = useMutation({
    mutationFn: () =>
      putCryptoBasket(userId, {
        items: normalizeItems(items)
      }),
    onSuccess: (basket) => {
      setItems(
        basket.items.map((item) => ({
          id: item.id,
          sort_order: item.sort_order,
          symbol: item.symbol,
          enabled: item.enabled
        }))
      );
      void queryClient.invalidateQueries({ queryKey: ["crypto-basket", userId] });
    }
  });

  const syncMutation = useMutation({
    mutationFn: () => syncCryptoBasket(userId),
    onSuccess: (response) => {
      setItems(
        response.basket.items.map((item) => ({
          id: item.id,
          sort_order: item.sort_order,
          symbol: item.symbol,
          enabled: item.enabled
        }))
      );
      void queryClient.invalidateQueries({ queryKey: ["crypto-basket", userId] });
      void queryClient.invalidateQueries({ queryKey: ["dashboard", userId] });
      void queryClient.invalidateQueries({ queryKey: ["positions", userId] });
    }
  });

  function addItem() {
    const symbol = newSymbol.trim().toUpperCase();
    if (!symbol) {
      return;
    }
    setItems((current) => [
      ...current,
      {
        id: null,
        sort_order: current.length,
        symbol,
        enabled: true
      }
    ]);
    setNewSymbol("");
  }

  function updateItem(index: number, patch: Partial<DraftItem>) {
    setItems((current) =>
      current.map((item, itemIndex) =>
        itemIndex === index
          ? { ...item, ...patch, symbol: patch.symbol?.toUpperCase() ?? item.symbol }
          : item
      )
    );
  }

  function moveItem(index: number, direction: -1 | 1) {
    setItems((current) => {
      const targetIndex = index + direction;
      if (targetIndex < 0 || targetIndex >= current.length) {
        return current;
      }
      const next = [...current];
      const [item] = next.splice(index, 1);
      next.splice(targetIndex, 0, item);
      return next.map((entry, sortOrder) => ({ ...entry, sort_order: sortOrder }));
    });
  }

  function deleteItem(index: number) {
    setItems((current) =>
      current
        .filter((_, itemIndex) => itemIndex !== index)
        .map((entry, sortOrder) => ({ ...entry, sort_order: sortOrder }))
    );
  }

  if (basketQuery.isLoading) {
    return <p className="text-sm text-slate-600">Loading basket.</p>;
  }

  if (basketQuery.isError) {
    return <p className="text-sm text-red-700">{(basketQuery.error as Error).message}</p>;
  }

  const latestRuns = syncMutation.data?.runs ?? [];
  const hasEnabledItems = items.some((item) => item.enabled);

  return (
    <div className="space-y-5">
      <section className="rounded-md border border-stone-200 bg-white p-4 shadow-soft">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
          <label className="block max-w-sm flex-1">
            <span className="text-sm font-medium text-slate-700">Symbol</span>
            <input
              className="mt-1 h-10 w-full rounded-md border border-stone-300 bg-white px-3 text-sm uppercase outline-none focus:border-teal-600"
              value={newSymbol}
              onChange={(event) => setNewSymbol(event.target.value.toUpperCase())}
              placeholder="BTC_USDT"
            />
          </label>
          <div className="flex flex-wrap gap-2">
            <button
              className="inline-flex h-10 items-center justify-center gap-2 rounded-md border border-stone-300 bg-white px-4 text-sm font-medium text-slate-800 hover:bg-stone-50 disabled:cursor-not-allowed disabled:text-slate-400"
              type="button"
              onClick={addItem}
              disabled={!newSymbol.trim()}
            >
              <Plus className="h-4 w-4" aria-hidden="true" />
              Add
            </button>
            <button
              className="inline-flex h-10 items-center justify-center gap-2 rounded-md bg-slate-900 px-4 text-sm font-medium text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-400"
              type="button"
              onClick={() => saveMutation.mutate()}
              disabled={saveMutation.isPending}
            >
              <Check className="h-4 w-4" aria-hidden="true" />
              {saveMutation.isPending ? "Saving..." : "Save"}
            </button>
            <button
              className="inline-flex h-10 items-center justify-center gap-2 rounded-md bg-teal-700 px-4 text-sm font-medium text-white hover:bg-teal-800 disabled:cursor-not-allowed disabled:bg-slate-400"
              type="button"
              onClick={() => syncMutation.mutate()}
              disabled={syncMutation.isPending || !hasEnabledItems}
            >
              <RefreshCw className="h-4 w-4" aria-hidden="true" />
              {syncMutation.isPending ? "Syncing..." : "Sync now"}
            </button>
          </div>
        </div>
        {saveMutation.isError ? (
          <p className="mt-3 text-sm text-red-700">{(saveMutation.error as Error).message}</p>
        ) : null}
        {syncMutation.isError ? (
          <p className="mt-3 text-sm text-red-700">{(syncMutation.error as Error).message}</p>
        ) : null}
      </section>

      <section className="space-y-3">
        {items.length === 0 ? (
          <div className="rounded-md border border-dashed border-stone-300 bg-white px-4 py-8 text-sm text-slate-600">
            No basket symbols yet.
          </div>
        ) : null}
        {items.map((item, index) => (
          <BasketItemRow
            key={`${item.id ?? "new"}-${index}`}
            item={item}
            index={index}
            status={statusBySymbol.get(item.symbol)}
            onUpdate={(patch) => updateItem(index, patch)}
            onMove={(direction) => moveItem(index, direction)}
            onDelete={() => deleteItem(index)}
            canMoveUp={index > 0}
            canMoveDown={index < items.length - 1}
          />
        ))}
      </section>

      {latestRuns.length ? <SyncRunSummary runs={latestRuns} /> : null}
    </div>
  );
}

function BasketItemRow({
  item,
  index,
  status,
  onUpdate,
  onMove,
  onDelete,
  canMoveUp,
  canMoveDown
}: {
  item: DraftItem;
  index: number;
  status: CryptoBasketItem | undefined;
  onUpdate: (patch: Partial<DraftItem>) => void;
  onMove: (direction: -1 | 1) => void;
  onDelete: () => void;
  canMoveUp: boolean;
  canMoveDown: boolean;
}) {
  return (
    <article className="rounded-md border border-stone-200 bg-white p-4 shadow-soft">
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-start">
        <div className="grid gap-3 md:grid-cols-[minmax(10rem,18rem)_auto_minmax(0,1fr)] md:items-center">
          <label className="block">
            <span className="text-xs font-medium text-slate-600">Symbol {index + 1}</span>
            <input
              className="mt-1 h-10 w-full rounded-md border border-stone-300 bg-white px-3 text-sm uppercase outline-none focus:border-teal-600"
              value={item.symbol}
              onChange={(event) => onUpdate({ symbol: event.target.value })}
              placeholder="BTC_USDT"
            />
          </label>
          <label className="inline-flex items-center gap-2 text-sm text-slate-700">
            <input
              className="h-4 w-4 rounded border-stone-300 text-teal-700"
              type="checkbox"
              checked={item.enabled}
              onChange={(event) => onUpdate({ enabled: event.target.checked })}
            />
            Enabled
          </label>
          <SyncStatus item={status} />
        </div>
        <div className="flex gap-2">
          <IconButton label="Move up" disabled={!canMoveUp} onClick={() => onMove(-1)}>
            <ArrowUp className="h-4 w-4" aria-hidden="true" />
          </IconButton>
          <IconButton label="Move down" disabled={!canMoveDown} onClick={() => onMove(1)}>
            <ArrowDown className="h-4 w-4" aria-hidden="true" />
          </IconButton>
          <IconButton label="Delete" onClick={onDelete}>
            <Trash2 className="h-4 w-4" aria-hidden="true" />
          </IconButton>
        </div>
      </div>
    </article>
  );
}

function SyncStatus({ item }: { item: CryptoBasketItem | undefined }) {
  if (!item) {
    return <p className="text-sm text-slate-600">Not saved.</p>;
  }
  const tone = {
    idle: "bg-slate-100 text-slate-700",
    running: "bg-sky-100 text-sky-800",
    success: "bg-emerald-100 text-emerald-800",
    error: "bg-red-100 text-red-800"
  }[item.sync_status];

  return (
    <div className="space-y-1 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <span className={`rounded px-2 py-1 text-xs font-semibold uppercase ${tone}`}>
          {item.sync_status}
        </span>
        <span className="text-slate-600">Last success {formatDateTime(item.last_successful_sync_at)}</span>
      </div>
      <p className="text-xs text-slate-500">
        Imported {item.last_imported}, skipped {item.last_skipped_duplicates}, positions{" "}
        {item.last_positions_created}
      </p>
      {item.last_error ? <p className="text-xs text-red-700">{item.last_error}</p> : null}
      {item.last_warnings.length ? (
        <p className="text-xs text-amber-800">{item.last_warnings.join(" ")}</p>
      ) : null}
    </div>
  );
}

function SyncRunSummary({ runs }: { runs: CryptoBasketSyncRun[] }) {
  return (
    <section className="rounded-md border border-stone-200 bg-white p-4 shadow-soft">
      <h2 className="text-lg font-semibold text-slate-950">Latest sync</h2>
      <div className="mt-3 divide-y divide-stone-100">
        {runs.map((run) => (
          <div key={run.id} className="grid gap-2 py-3 text-sm md:grid-cols-[9rem_7rem_1fr]">
            <span className="font-medium text-slate-950">{run.symbol}</span>
            <span className={run.status === "error" ? "text-red-700" : "text-slate-700"}>
              {run.status}
            </span>
            <span className="text-slate-600">
              Imported {run.imported}, skipped {run.skipped_duplicates}, reconstructed{" "}
              {run.positions_created} positions
              {run.error ? `: ${run.error}` : ""}
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}

function IconButton({
  label,
  disabled,
  onClick,
  children
}: {
  label: string;
  disabled?: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      aria-label={label}
      title={label}
      className="inline-flex h-9 w-9 items-center justify-center rounded-md border border-stone-300 bg-white text-slate-700 hover:bg-stone-50 disabled:cursor-not-allowed disabled:text-slate-300"
      type="button"
      onClick={onClick}
      disabled={disabled}
    >
      {children}
    </button>
  );
}

function normalizeItems(items: DraftItem[]): DraftItem[] {
  return items.map((item, sortOrder) => ({
    id: item.id ?? null,
    sort_order: sortOrder,
    symbol: item.symbol.trim().toUpperCase(),
    enabled: item.enabled
  }));
}
