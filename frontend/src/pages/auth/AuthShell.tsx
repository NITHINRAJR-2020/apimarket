import { ReactNode } from "react";

export default function AuthShell({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle: string;
  children: ReactNode;
}) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-ink-bg px-4 py-10">
      <div className="w-full max-w-md">
        <div className="mb-8 text-center">
          <div className="font-display text-2xl font-semibold tracking-tight text-paper">
            PayperQuery
          </div>
          <p className="mt-1 text-sm text-paper-dim">
            The escrow-backed marketplace for agent-to-API payments
          </p>
        </div>
        <div className="rounded-xl border border-ink-line bg-ink-panel p-8 shadow-sm">
          <h1 className="font-display text-xl font-semibold text-paper">{title}</h1>
          <p className="mb-6 mt-1 text-sm text-paper-muted">{subtitle}</p>
          {children}
        </div>
      </div>
    </div>
  );
}
