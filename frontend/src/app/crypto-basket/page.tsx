"use client";

import { CryptoBasketForm } from "@/components/CryptoBasketForm";
import { EmptyState } from "@/components/EmptyState";
import { useDevelopmentUserId } from "@/lib/storage";

export default function CryptoBasketPage() {
  const { userId, isReady } = useDevelopmentUserId();

  if (!isReady) {
    return <EmptyState title="Loading workspace">Preparing your local workspace.</EmptyState>;
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-slate-950">Crypto Basket</h1>
        <p className="mt-1 max-w-2xl text-sm text-slate-600">
          Enabled MEXC Futures symbols are synced automatically by the backend.
        </p>
      </div>
      {userId ? (
        <CryptoBasketForm userId={userId} />
      ) : (
        <EmptyState title="Add a development user ID">
          Paste a backend user UUID in the header before editing the basket.
        </EmptyState>
      )}
    </div>
  );
}
