import { useEffect, useState } from "react";
import { api } from "../services/api";
import type { Transaction, TransactionStatus } from "../types";
import { Card } from "../components/Card";
import StatusBadge from "../components/StatusBadge";
import EmptyState from "../components/EmptyState";
import { formatDate, formatMicro, shortAddr } from "../lib/format";

const STATUSES: TransactionStatus[] = [
  "ESCROW_HELD",
  "SERVICE_COMPLETED",
  "REFUNDED",
  "POLICY_BLOCKED",
  "DISPUTED",
  "FAILED",
];

export default function TransactionsPage() {
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api
      .listTransactions(statusFilter ? { status_filter: statusFilter } : undefined)
      .then(setTransactions)
      .finally(() => setLoading(false));
  }, [statusFilter]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-2xl font-semibold text-paper">Transactions</h1>
        <p className="mt-1 text-sm text-paper-dim">Every purchase attempt, from policy check through settlement.</p>
      </div>

      <div className="flex flex-wrap gap-2">
        <FilterChip active={statusFilter === ""} onClick={() => setStatusFilter("")} label="All" />
        {STATUSES.map((s) => (
          <FilterChip key={s} active={statusFilter === s} onClick={() => setStatusFilter(s)} label={s.replace(/_/g, " ")} />
        ))}
      </div>

      {loading ? (
        <p className="text-sm text-paper-dim">Loading…</p>
      ) : transactions.length === 0 ? (
        <EmptyState title="No transactions match this filter" />
      ) : (
        <Card className="divide-y divide-ink-line p-0">
          {transactions.map((t) => (
            <div key={t.id} className="flex flex-wrap items-center justify-between gap-3 px-5 py-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <StatusBadge status={t.status} />
                  {t.deposit_tx_id && <span className="mono-chip text-[11px] text-paper-dim">{shortAddr(t.deposit_tx_id)}</span>}
                </div>
                <div className="mt-1 text-xs text-paper-dim">
                  {t.payer_address && <>paid from <span className="mono-chip">{shortAddr(t.payer_address)}</span> · </>}
                  {formatDate(t.created_at)}
                  {t.failure_reason && <span className="text-vault-red"> · {t.failure_reason}</span>}
                </div>
              </div>
              <div className="text-right">
                <div className="font-mono text-sm text-paper">{formatMicro(t.amount_microalgos)}</div>
                {t.response_status_code && (
                  <div className="text-[11px] text-paper-dim">upstream {t.response_status_code}</div>
                )}
              </div>
            </div>
          ))}
        </Card>
      )}
    </div>
  );
}

function FilterChip({ active, onClick, label }: { active: boolean; onClick: () => void; label: string }) {
  return (
    <button
      onClick={onClick}
      className={`rounded-full px-3 py-1 font-mono text-[11px] uppercase tracking-wide transition-colors ${
        active ? "bg-brass text-ink-bg" : "border border-ink-line2 text-paper-muted hover:border-brass/50 hover:text-brass-bright"
      }`}
    >
      {label}
    </button>
  );
}
