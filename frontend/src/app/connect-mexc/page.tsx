import { MexcConnectionForm } from "@/components/MexcConnectionForm";

export default function ConnectMexcPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-slate-950">Connect MEXC</h1>
        <p className="mt-1 max-w-2xl text-sm text-slate-600">
          This MVP prepares the connection flow. Credential storage is intentionally not wired until
          backend credential management is added.
        </p>
      </div>
      <MexcConnectionForm />
    </div>
  );
}
