import { ReactNode } from "react";

export function EmptyState({
  title,
  children
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <div className="rounded-md border border-dashed border-stone-300 bg-white px-4 py-8 text-center">
      <h2 className="text-sm font-semibold text-slate-950">{title}</h2>
      <div className="mx-auto mt-2 max-w-xl text-sm text-slate-600">{children}</div>
    </div>
  );
}
