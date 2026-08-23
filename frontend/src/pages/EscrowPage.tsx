import { useEffect, useState } from "react";
import { api } from "../services/api";
import type { Escrow, EscrowStatus } from "../types";
import { Card } from "../components/Card";
import StatusBadge from "../components/StatusBadge";
import EmptyState from "../components/EmptyState";
import LedgerTracker from "../components/LedgerTracker";
import { formatDate, formatMicro } from "../lib/format";

const STATUSES: EscrowStatus[] = ["HELD", "RELEASED", "REFUNDED", "DISPUTED"];

export default function EscrowPage() {
  const [escrows, setEscrows] = useState<Escrow[]>([]);
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [actionError, setActionError] = useState<string | null>(null);

  async function refresh() {
    setLoading(true);
    setEscrows(await api.listEscrows(statusFilter || undefined));
    setLoading(false);
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusFilter]);

  async function handleRelease(id: string) {
    setActionError(null);
    try {
      await api.releaseEscrow(id, "Manually released from the admin ledger");
      await refresh();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Release failed");
    }
  }

  async function handleRefund(id: string) {
    setActionError(null);
    try {
      await api.refundEscrow(id, "Manually refunded from the admin ledger");
      await refresh();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Refund failed");
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-2xl font-semibold text-paper">Escrow ledger</h1>
        <p className="mt-1 text-sm text-paper-dim">
          Every deposit into platform custody, and the real on-chain transaction that eventually moved it onward.
        </p>
      </div>

      <div className="flex flex-wrap gap-2">
        <FilterChip active={statusFilter === ""} onClick={() => setStatusFilter("")} label="All" />
        {STATUSES.map((s) => (
          <FilterChip key={s} active={statusFilter === s} onClick={() => setStatusFilter(s)} label={s} />
        ))}
      </div>

      {actionError && (
        <Card className="border-vault-red/40">
          <p className="text-xs text-vault-red">{actionError}</p>
        </Card>
      )}

      {loading ? (
        <p className="text-sm text-paper-dim">Loading…</p>
      ) : escrows.length === 0 ? (
        <EmptyState title="No escrow records match this filter" />
      ) : (
        <div className="space-y-3">
          {escrows.map((e) => (
            <Card key={e.id}>
              <div className="flex flex-wrap items-center justify-between gap-4">
                <div className="space-y-2">
                  <div className="flex items-center gap-2">
                    <StatusBadge status={e.status} />
                    <span className="font-mono text-sm text-paper">{formatMicro(e.amount_microalgos)}</span>
                    <span className="text-xs text-paper-dim">held {formatDate(e.created_at)}</span>
                  </div>
                  <LedgerTracker
                    status={e.status}
                    depositTxId={e.deposit_tx_id}
                    payoutTxId={e.payout_tx_id}
                    refundTxId={e.refund_tx_id}
                  />
                  {e.notes && <p className="text-xs text-paper-dim">{e.notes}</p>}
                </div>

                {(e.status === "HELD" || e.status === "DISPUTED") && (
                  <div className="flex shrink-0 gap-2">
                    <button
                      onClick={() => handleRelease(e.id)}
                      className="rounded-md border border-vault-green/40 px-3 py-1.5 text-xs font-medium text-vault-green hover:bg-vault-green/10"
                    >
                      Release to provider
                    </button>
                    <button
                      onClick={() => handleRefund(e.id)}
                      className="rounded-md border border-vault-blue/40 px-3 py-1.5 text-xs font-medium text-vault-blue hover:bg-vault-blue/10"
                    >
                      Refund to agent
                    </button>
                  </div>
                )}
              </div>
            </Card>
          ))}
        </div>
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
