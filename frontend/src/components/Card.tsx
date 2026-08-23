import type { ReactNode } from "react";

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div className={`rounded-lg border border-ink-line bg-ink-panel p-5 ${className}`}>
      {children}
    </div>
  );
}

export function StatCard({
  label,
  value,
  hint,
  tone = "default",
}: {
  label: string;
  value: string | number;
  hint?: string;
  tone?: "default" | "brass" | "green" | "red";
}) {
  const toneClass = {
    default: "text-paper",
    brass: "text-brass-bright",
    green: "text-vault-green",
    red: "text-vault-red",
  }[tone];

  return (
    <Card>
      <div className="font-mono text-[11px] uppercase tracking-widest text-paper-dim">{label}</div>
      <div className={`mt-2 font-display text-3xl font-semibold ${toneClass}`}>{value}</div>
      {hint && <div className="mt-1 text-xs text-paper-dim">{hint}</div>}
    </Card>
  );
}
