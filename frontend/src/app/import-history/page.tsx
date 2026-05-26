"use client";

import { EmptyState } from "@/components/EmptyState";
import { ImportHistoryForm } from "@/components/ImportHistoryForm";
import { useDevelopmentUserId } from "@/lib/storage";

export default function ImportHistoryPage() {
  const { userId, isReady } = useDevelopmentUserId();

  if (!isReady) {
    return <EmptyState title="Loading workspace">Preparing your local workspace.</EmptyState>;
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-slate-950">Import history</h1>
        <p className="mt-1 max-w-2xl text-sm text-slate-600">
          Import read-only MEXC Futures order deals. These fills are used later to reconstruct
          positions for review.
        </p>
      </div>
      {userId ? (
        <ImportHistoryForm userId={userId} />
      ) : (
        <EmptyState title="Add a development user ID">
          Paste a backend user UUID in the header before importing history.
        </EmptyState>
      )}
    </div>
  );
}
