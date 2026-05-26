"use client";

import { ShieldCheck } from "lucide-react";
import { FormEvent, useState } from "react";

export function MexcConnectionForm() {
  const [accessKey, setAccessKey] = useState("");
  const [secretKey, setSecretKey] = useState("");
  const [confirmedReadOnly, setConfirmedReadOnly] = useState(false);
  const [savedMessage, setSavedMessage] = useState("");

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSecretKey("");
    setSavedMessage(
      accessKey && confirmedReadOnly
        ? "Secret cleared. Backend credential storage is not connected in this MVP."
        : "Confirm the read-only checklist before continuing."
    );
  }

  return (
    <form className="max-w-2xl space-y-4" onSubmit={handleSubmit}>
      <div className="rounded-md border border-teal-200 bg-teal-50 px-4 py-3 text-sm text-teal-900">
        Use a read-only MEXC Futures API key. Do not enable order placement, transfer, or withdrawal permissions.
      </div>
      <label className="block">
        <span className="text-sm font-medium text-slate-700">Access key</span>
        <input
          className="mt-1 h-10 w-full rounded-md border border-stone-300 bg-white px-3 text-sm outline-none focus:border-teal-600"
          value={accessKey}
          onChange={(event) => setAccessKey(event.target.value)}
          placeholder="MEXC access key"
          autoComplete="off"
        />
      </label>
      <label className="block">
        <span className="text-sm font-medium text-slate-700">Secret key</span>
        <input
          className="mt-1 h-10 w-full rounded-md border border-stone-300 bg-white px-3 text-sm outline-none focus:border-teal-600"
          value={secretKey}
          onChange={(event) => setSecretKey(event.target.value)}
          placeholder="Paste secret for this session only"
          type="password"
          autoComplete="off"
        />
      </label>
      <label className="flex items-start gap-3 rounded-md border border-stone-200 bg-white px-4 py-3 text-sm text-slate-700">
        <input
          className="mt-1"
          checked={confirmedReadOnly}
          onChange={(event) => setConfirmedReadOnly(event.target.checked)}
          type="checkbox"
        />
        <span>
          I checked the MEXC permissions and this key is for read-only history review.
        </span>
      </label>
      <button
        className="inline-flex h-10 items-center justify-center gap-2 rounded-md bg-slate-900 px-4 text-sm font-medium text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-400"
        type="submit"
        disabled={!accessKey || !secretKey}
      >
        <ShieldCheck className="h-4 w-4" aria-hidden="true" />
        Check connection setup
      </button>
      {savedMessage ? <p className="text-sm text-slate-600">{savedMessage}</p> : null}
    </form>
  );
}
