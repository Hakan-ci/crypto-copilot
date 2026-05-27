import { MexcConnectionForm } from "@/components/MexcConnectionForm";

export default function ConnectMexcPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-slate-950">Connect MEXC</h1>
        <p className="mt-1 max-w-2xl text-sm text-slate-600">
          Backend `.env` credentials are used for read-only MEXC Futures history.
        </p>
      </div>
      <MexcConnectionForm />
    </div>
  );
}
