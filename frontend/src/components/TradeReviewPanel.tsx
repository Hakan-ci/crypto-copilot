"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Sparkles } from "lucide-react";

import { TimeframeSelector } from "@/components/TimeframeSelector";
import { generateReview } from "@/lib/api";
import { timeframeLabel } from "@/lib/timeframes";
import type {
  AiTradeReview,
  Timeframe,
  TradeReviewOutput,
  TradingPlanRuleResult
} from "@/lib/types";

function readReview(review: AiTradeReview | null): TradeReviewOutput | null {
  if (!review) {
    return null;
  }
  const payload = review.review_json as Partial<TradeReviewOutput>;
  if (typeof payload.summary === "string") {
    return payload as TradeReviewOutput;
  }
  return {
    summary: review.summary,
    timeframe_alignment: {
      one_hour: "unknown",
      four_hour: "unknown",
      one_day: "unknown",
      overall: "unknown"
    },
    indicator_observations: {
      rsi: [],
      stoch_rsi: [],
      macd: [],
      supertrend: []
    },
    strengths: [],
    weaknesses: [],
    risk_flags: [],
    mistake_tags: review.mistake_tags,
    rule_match_score: review.rule_match_score,
    risk_score: review.risk_score,
    execution_score: review.execution_score,
    final_note: "Final decision belongs to the user.",
    transaction_timeline: [],
    entry_analysis: [],
    exit_analysis: [],
    plan_compliance: [],
    execution_notes: [],
    missed_context: [],
    follow_up_questions: [],
    abandoned_rules: [],
    rule_violations: [],
    trading_plan_rule_results: []
  };
}

function notFollowedRules(reviewOutput: TradeReviewOutput | null): TradingPlanRuleResult[] {
  if (!reviewOutput) {
    return [];
  }
  const structuredResults = reviewOutput.trading_plan_rule_results ?? [];
  if (structuredResults.length > 0) {
    return structuredResults.filter((result) => result.status === "not_followed");
  }

  const legacyRules =
    reviewOutput.rule_violations?.length
      ? reviewOutput.rule_violations
      : reviewOutput.abandoned_rules ?? [];
  return legacyRules.map((ruleLine) => {
    const [titlePart, detailPart] = ruleLine.split(":");
    const reason = detailPart?.includes(" - ")
      ? detailPart.split(" - ").slice(1).join(" - ").trim()
      : (detailPart ?? ruleLine).trim();
    return {
      title: titlePart?.trim() || "Trading plan rule",
      status: "not_followed",
      reason: reason || "This rule was not followed."
    };
  });
}

export function TradeReviewPanel({
  positionId,
  review,
  snapshotsReady,
  reviewTimeframe,
  onReviewTimeframeChange
}: {
  positionId: string;
  review: AiTradeReview | null;
  snapshotsReady: boolean;
  reviewTimeframe: Timeframe;
  onReviewTimeframeChange: (value: Timeframe) => void;
}) {
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: () => generateReview(positionId, reviewTimeframe),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["position-detail", positionId] });
    },
    onError: () => {
      void queryClient.invalidateQueries({ queryKey: ["position-detail", positionId] });
    }
  });
  const reviewOutput = mutation.data?.review ?? readReview(review);
  const rulesNotFollowed = notFollowedRules(reviewOutput);
  const ruleScore = reviewOutput?.rule_match_score;

  return (
    <section className="rounded-md border border-stone-200 bg-white p-4 shadow-soft">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2 className="text-lg font-semibold text-slate-950">AI trade review</h2>
          <p className="mt-1 text-sm text-slate-600">
            Saved trading plan rule compliance.
          </p>
        </div>
        <div className="flex flex-col gap-2 sm:items-end">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-slate-700">Trade timeframe</span>
            <TimeframeSelector
              value={reviewTimeframe}
              onChange={(value) => {
                if (value !== "all") {
                  onReviewTimeframeChange(value);
                }
              }}
            />
          </div>
          <button
            className="inline-flex h-10 items-center justify-center gap-2 rounded-md bg-slate-900 px-4 text-sm font-medium text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-400"
            type="button"
            disabled={mutation.isPending || !snapshotsReady}
            onClick={() => mutation.mutate()}
          >
            <Sparkles className="h-4 w-4" aria-hidden="true" />
            {mutation.isPending ? "Generating..." : "Generate Review"}
          </button>
        </div>
      </div>
      {mutation.isError ? (
        <p className="mt-3 text-sm text-red-700">{(mutation.error as Error).message}</p>
      ) : null}
      {!snapshotsReady ? (
        <p className="mt-3 text-sm text-amber-700">
          Prepare the {timeframeLabel(reviewTimeframe)} entry snapshot before generating an AI review.
        </p>
      ) : null}
      {reviewOutput ? (
        <div className="mt-4 space-y-4">
          <div className="rounded-md border border-stone-200 bg-stone-50 px-3 py-2">
            <p className="text-xs font-medium uppercase tracking-[0.12em] text-slate-500">
              Rules followed
            </p>
            <p className="mt-1 text-lg font-semibold text-slate-950">
              {typeof ruleScore === "number" ? `${ruleScore}%` : "-"}
            </p>
          </div>
          {rulesNotFollowed.length > 0 ? (
            <NotFollowedRules items={rulesNotFollowed} />
          ) : (
            <p className="rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800">
              {typeof ruleScore === "number"
                ? "All saved trading plan rules were followed."
                : "No saved trading plan rules were available."}
            </p>
          )}
        </div>
      ) : (
        <p className="mt-4 text-sm text-slate-600">
          No review is saved yet. Generate one after snapshots are available.
        </p>
      )}
    </section>
  );
}

function NotFollowedRules({
  items
}: {
  items: TradingPlanRuleResult[];
}) {
  return (
    <div>
      <h3 className="text-sm font-semibold text-slate-950">Rules not followed</h3>
      <div className="mt-2 grid gap-2">
        {items.map((item, index) => (
          <article
            key={`${item.title}-${index}`}
            className="rounded-md border border-red-100 bg-red-50 px-3 py-2"
          >
            <h4 className="text-sm font-semibold text-red-900">{item.title}</h4>
            <p className="mt-1 text-sm leading-6 text-red-800">{item.reason}</p>
          </article>
        ))}
      </div>
    </div>
  );
}
