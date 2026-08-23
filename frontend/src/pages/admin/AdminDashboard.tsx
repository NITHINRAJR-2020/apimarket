import { useEffect, useState } from "react";
import { api } from "../../services/api";
import type { AdminStats, Transaction } from "../../types";
import { Card, StatCard } from "../../components/Card";
import StatusBadge from "../../components/StatusBadge";
import EmptyState from "../../components/EmptyState";
import { formatDate, formatMicro, shortAddr } from "../../lib/format";

export default function AdminDashboard() {
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [recent, setRecent] = useState<Transaction[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.adminStats(), api.listTransactions()])
      .then(([s, txns]) => {
        setStats(s);
        setRecent(txns.slice(0, 8));
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <p className="text-paper-muted">Loading…</p>;
  if (error) return <p className="text-vault-red">{error}</p>;
  if (!stats) return null;

  return (
    <div className="space-y-8">
      <div>
        <h1 className="font-display text-2xl font-semibold text-paper">System overview</h1>
        <p className="mt-1 text-sm text-paper-muted">Everything happening across PayperQuery.</p>
      </div>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label="Total users" value={stats.users.total} hint={`${stats.users.active} active`} />
        <StatCard label="Publishers" value={stats.users.publishers} tone="brass" />
        <StatCard label="APIs" value={stats.listings.total} hint={`${stats.listings.active} active`} />
        <StatCard label="Agents" value={stats.agents.total} hint={`${stats.agents.paused} paused`} />
      </div>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label="Transactions" value={stats.transactions.total} />
        <StatCard label="Escrow held" value={stats.escrow.held} tone="brass" />
        <StatCard label="Released" value={stats.escrow.released} tone="green" />
        <StatCard label="Disputed" value={stats.escrow.disputed} tone={stats.escrow.disputed ? "red" : "default"} />
      </div>

      <div>
        <h2 className="mb-3 font-display text-lg font-semibold text-paper">Recent activity</h2>
        {recent.length === 0 ? (
          <EmptyState title="No transactions yet" hint="Purchases will appear here as agents buy APIs." />
        ) : (
          <Card className="overflow-hidden p-0">
            <table className="w-full text-sm">
              <thead className="border-b border-ink-line text-left text-xs uppercase tracking-wider text-paper-dim">
                <tr>
                  <th className="px-4 py-3 font-medium">Transaction</th>
                  <th className="px-4 py-3 font-medium">Amount</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                  <th className="px-4 py-3 font-medium">When</th>
                </tr>
              </thead>
              <tbody>
                {recent.map((t) => (
                  <tr key={t.id} className="border-b border-ink-line last:border-0">
                    <td className="px-4 py-3 font-mono text-xs text-paper-muted">{shortAddr(t.id)}</td>
                    <td className="px-4 py-3">{formatMicro(t.amount_microalgos)}</td>
                    <td className="px-4 py-3"><StatusBadge status={t.status} /></td>
                    <td className="px-4 py-3 text-paper-muted">{formatDate(t.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        )}
      </div>
    </div>
  );
}
