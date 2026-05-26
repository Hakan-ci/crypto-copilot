import { TradingPlanForm } from "@/components/TradingPlanForm";

export default function TradingPlanPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-slate-950">Trading plan</h1>
        <p className="mt-1 max-w-2xl text-sm text-slate-600">
          Save simple review rules locally. They are included as optional context when you generate
          a trade review.
        </p>
      </div>
      <TradingPlanForm />
    </div>
  );
}
