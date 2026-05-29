import { TradingPlanForm } from "@/components/TradingPlanForm";

export default function TradingPlanPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-slate-950">Trading plan</h1>
        <p className="mt-1 max-w-2xl text-sm text-slate-600">
          Define ordered system rules with titles and descriptions for trade reviews.
        </p>
      </div>
      <TradingPlanForm />
    </div>
  );
}
