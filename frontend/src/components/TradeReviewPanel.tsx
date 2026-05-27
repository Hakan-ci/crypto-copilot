"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Sparkles } from "lucide-react";

import { generateReview } from "@/lib/api";
import type { AiTradeReview, TradeReviewOutput } from "@/lib/types";

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
    follow_up_questions: []
  };
}

export function TradeReviewPanel({
  positionId,
  review,
  snapshotsReady
}: {
  positionId: string;
  review: AiTradeReview | null;
  snapshotsReady: boolean;
}) {
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: () => generateReview(positionId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["position-detail", positionId] });
    }
  });
  const reviewOutput = mutation.data?.review ?? readReview(review);

  return (
    <section className="rounded-md border border-stone-200 bg-white p-4 shadow-soft">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2 className="text-lg font-semibold text-slate-950">AI trade review</h2>
          <p className="mt-1 text-sm text-slate-600">
            Educational review of this completed position and its stored indicators.
          </p>
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
      {mutation.isError ? (
        <p className="mt-3 text-sm text-red-700">{(mutation.error as Error).message}</p>
      ) : null}
      {!snapshotsReady ? (
        <p className="mt-3 text-sm text-amber-700">
          Prepare 1H, 4H, and 1D snapshots before generating an AI review.
        </p>
      ) : null}
      {reviewOutput ? (
        <div className="mt-4 space-y-4">
          <p className="text-sm leading-6 text-slate-700">{reviewOutput.summary}</p>
          <div className="grid gap-3 md:grid-cols-3">
            {[
              ["Rule match", reviewOutput.rule_match_score],
              ["Risk", reviewOutput.risk_score],
              ["Execution", reviewOutput.execution_score]
            ].map(([label, score]) => (
              <div key={label} className="rounded-md border border-stone-200 bg-stone-50 px-3 py-2">
                <p className="text-xs font-medium uppercase tracking-[0.12em] text-slate-500">
                  {label}
                </p>
                <p className="mt-1 text-lg font-semibold text-slate-950">{score ?? "-"}</p>
              </div>
            ))}
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            <ReviewList title="Strengths" items={reviewOutput.strengths} />
            <ReviewList title="Weaknesses" items={reviewOutput.weaknesses} />
            <ReviewList title="Risk flags" items={reviewOutput.risk_flags} />
            <ReviewList title="Mistake tags" items={reviewOutput.mistake_tags} />
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            <ReviewList
              title="Transaction timing"
              items={reviewOutput.transaction_timeline ?? []}
            />
            <ReviewList title="Plan compliance" items={reviewOutput.plan_compliance ?? []} />
            <ReviewList title="Entry analysis" items={reviewOutput.entry_analysis ?? []} />
            <ReviewList title="Exit analysis" items={reviewOutput.exit_analysis ?? []} />
            <ReviewList title="Execution notes" items={reviewOutput.execution_notes ?? []} />
            <ReviewList title="Missed context" items={reviewOutput.missed_context ?? []} />
          </div>
          <ReviewList
            title="Follow-up questions"
            items={reviewOutput.follow_up_questions ?? []}
          />
          <p className="rounded-md bg-stone-50 px-3 py-2 text-sm text-slate-700">
            {reviewOutput.final_note}
          </p>
        </div>
      ) : (
        <p className="mt-4 text-sm text-slate-600">
          No review is saved yet. Generate one after snapshots are available.
        </p>
      )}
    </section>
  );
}

function ReviewList({ title, items }: { title: string; items: string[] }) {
  return (
    <div>
      <h3 className="text-sm font-semibold text-slate-950">{title}</h3>
      {items.length === 0 ? (
        <p className="mt-1 text-sm text-slate-500">No items yet.</p>
      ) : (
        <ul className="mt-2 space-y-1 text-sm text-slate-700">
          {items.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
