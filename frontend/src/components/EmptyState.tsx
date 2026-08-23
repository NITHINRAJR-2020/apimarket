export default function EmptyState({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="rounded-lg border border-dashed border-ink-line2 bg-ink-panel/50 px-6 py-10 text-center">
      <p className="font-display text-sm font-medium text-paper-muted">{title}</p>
      {hint && <p className="mt-1 text-xs text-paper-dim">{hint}</p>}
    </div>
  );
}
