"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Sparkles } from "lucide-react";
import { FormEvent, useState } from "react";

import { askAiQuestion, listAiQuestions } from "@/lib/api";
import { formatDateTime } from "@/lib/format";

export function AiQuestionPanel({ positionId }: { positionId: string }) {
  const [question, setQuestion] = useState("");
  const queryClient = useQueryClient();
  const questionsQuery = useQuery({
    queryKey: ["ai-questions", positionId],
    queryFn: () => listAiQuestions(positionId),
    enabled: Boolean(positionId)
  });
  const askMutation = useMutation({
    mutationFn: () => askAiQuestion(positionId, question),
    onSuccess: () => {
      setQuestion("");
      void queryClient.invalidateQueries({ queryKey: ["ai-questions", positionId] });
      void queryClient.invalidateQueries({ queryKey: ["position-detail", positionId] });
    },
    onError: () => {
      void queryClient.invalidateQueries({ queryKey: ["position-detail", positionId] });
    }
  });

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!question.trim() || askMutation.isPending) {
      return;
    }
    askMutation.mutate();
  }

  return (
    <section className="rounded-md border border-stone-200 bg-white p-4 shadow-soft">
      <div>
        <h2 className="text-lg font-semibold text-slate-950">Ask AI</h2>
        <p className="mt-1 text-sm text-slate-600">
          Ask retrospective questions about this position, its transactions, and the active plan.
        </p>
      </div>

      <form className="mt-4 space-y-3" onSubmit={handleSubmit}>
        <textarea
          className="min-h-24 w-full rounded-md border border-stone-300 bg-white px-3 py-2 text-sm outline-none focus:border-teal-600"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder="Ask about timing, execution, plan compliance, or indicator context."
        />
        <button
          className="inline-flex h-10 items-center justify-center gap-2 rounded-md bg-slate-900 px-4 text-sm font-medium text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-400"
          type="submit"
          disabled={askMutation.isPending || !question.trim()}
        >
          <Sparkles className="h-4 w-4" aria-hidden="true" />
          {askMutation.isPending ? "Answering..." : "Ask"}
        </button>
      </form>

      {askMutation.isError ? (
        <p className="mt-3 text-sm text-red-700">{(askMutation.error as Error).message}</p>
      ) : null}

      <div className="mt-5 space-y-3">
        {questionsQuery.isLoading ? (
          <p className="text-sm text-slate-600">Loading saved questions.</p>
        ) : null}
        {questionsQuery.isError ? (
          <p className="text-sm text-red-700">{(questionsQuery.error as Error).message}</p>
        ) : null}
        {questionsQuery.data?.length === 0 ? (
          <p className="text-sm text-slate-600">No saved questions yet.</p>
        ) : null}
        {questionsQuery.data?.map((item) => (
          <article key={item.id} className="rounded-md border border-stone-200 bg-stone-50 p-3">
            <div className="flex flex-col gap-1 sm:flex-row sm:items-start sm:justify-between">
              <h3 className="text-sm font-semibold text-slate-950">{item.question}</h3>
              <span className="text-xs text-slate-500">{formatDateTime(item.created_at)}</span>
            </div>
            <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-slate-700">
              {item.answer}
            </p>
          </article>
        ))}
      </div>
    </section>
  );
}
