"use client";

import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, RefreshCw, ShieldCheck } from "lucide-react";

import { getMexcReadiness } from "@/lib/api";

export function MexcConnectionForm() {
  const readinessQuery = useQuery({
    queryKey: ["mexc-readiness"],
    queryFn: () => getMexcReadiness(),
    retry: 1,
    refetchOnWindowFocus: false
  });
  const readiness = readinessQuery.data;
  const isReady = Boolean(
    readiness?.credentials_configured &&
      readiness.public_api_reachable &&
      readiness.private_read_authenticated
  );

  return (
    <section className="max-w-3xl space-y-4">
      <div
        className={`rounded-md border px-4 py-3 text-sm ${
          isReady
            ? "border-emerald-200 bg-emerald-50 text-emerald-900"
            : "border-amber-200 bg-amber-50 text-amber-900"
        }`}
      >
        <div className="flex items-start gap-3">
          {isReady ? (
            <ShieldCheck className="mt-0.5 h-4 w-4 flex-none" aria-hidden="true" />
          ) : (
            <AlertTriangle className="mt-0.5 h-4 w-4 flex-none" aria-hidden="true" />
          )}
          <p>
            {readinessQuery.isLoading
              ? "Checking MEXC read-only access."
              : readiness?.message ?? "MEXC readiness could not be checked."}
          </p>
        </div>
      </div>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatusPill label="Backend keys" value={readiness?.credentials_configured} />
        <StatusPill label="Base URL" text={readiness?.base_url ?? "-"} />
        <StatusPill label="Public API" value={readiness?.public_api_reachable} />
        <StatusPill label="Private read" value={readiness?.private_read_authenticated} />
      </div>
      <button
        className="inline-flex h-10 items-center justify-center gap-2 rounded-md border border-stone-300 bg-white px-4 text-sm font-medium text-slate-800 hover:bg-stone-100 disabled:cursor-not-allowed disabled:text-slate-400"
        type="button"
        disabled={readinessQuery.isFetching}
        onClick={() => void readinessQuery.refetch()}
      >
        <RefreshCw className="h-4 w-4" aria-hidden="true" />
        {readinessQuery.isFetching ? "Checking..." : "Check readiness"}
      </button>
      {readinessQuery.isError ? (
        <p className="text-sm text-red-700">{(readinessQuery.error as Error).message}</p>
      ) : null}
    </section>
  );
}

function StatusPill({
  label,
  value,
  text
}: {
  label: string;
  value?: boolean;
  text?: string;
}) {
  const display = text ?? (value ? "Ready" : "Missing");
  return (
    <div className="rounded-md border border-stone-200 bg-white px-4 py-3 shadow-soft">
      <p className="text-xs font-medium uppercase tracking-[0.12em] text-slate-500">{label}</p>
      <p className={`mt-1 text-sm font-semibold ${value === false ? "text-red-700" : "text-slate-950"}`}>
        {display}
      </p>
    </div>
  );
}
