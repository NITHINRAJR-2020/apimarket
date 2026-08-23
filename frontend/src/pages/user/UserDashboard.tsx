import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../services/api";
import type { Agent, Transaction } from "../../types";
import { Card, StatCard } from "../../components/Card";
import EmptyState from "../../components/EmptyState";
import StatusBadge from "../../components/StatusBadge";
import { formatDate, formatMicro, shortAddr } from "../../lib/format";

export default function UserDashboard() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [txns, setTxns] = useState<Transaction[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.listAgents(), api.listTransactions()])
      .then(([a, t]) => {
        setAgents(a);
        setTxns(t);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <p className="text-paper-muted">Loading…</p>;
  if (error) return <p className="text-vault-red">{error}</p>;

  const activeAgents = agents.filter((a) => a.is_active && !a.is_paused).length;
  const pausedAgents = agents.filter((a) => a.is_paused).length;

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-semibold text-paper">Your dashboard</h1>
          <p className="mt-1 text-sm text-paper-muted">Monitor your agents and their spending.</p>
        </div>
        <Link to="/user/agents" className="rounded-md bg-brass px-4 py-2 text-sm font-semibold text-white hover:bg-brass-bright">
          Manage agents
        </Link>
      </div>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label="Total agents" value={agents.length} />
        <StatCard label="Active" value={activeAgents} tone="green" />
        <StatCard label="Paused" value={pausedAgents} tone={pausedAgents ? "red" : "default"} />
        <StatCard label="Transactions" value={txns.length} tone="brass" />
      </div>

      <div>
        <h2 className="mb-3 font-display text-lg font-semibold text-paper">My agents</h2>
        {agents.length === 0 ? (
          <EmptyState title="No agents yet" hint="Create your first agent to start buying APIs." />
        ) : (
          <Card className="overflow-x-auto p-0">
            <table className="w-full text-sm">
              <thead className="border-b border-ink-line text-left text-xs uppercase tracking-wider text-paper-dim">
                <tr>
                  <th className="px-4 py-3 font-medium">Agent</th>
                  <th className="px-4 py-3 font-medium">Wallet</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                  <th className="px-4 py-3 font-medium">Created</th>
                </tr>
              </thead>
              <tbody>
                {agents.map((a) => (
                  <tr key={a.id} className="border-b border-ink-line last:border-0">
                    <td className="px-4 py-3 font-medium text-paper">{a.name}</td>
                    <td className="px-4 py-3 font-mono text-xs text-paper-muted">{shortAddr(a.wallet_address)}</td>
                    <td className="px-4 py-3">
                      {a.is_paused ? (
                        <span className="text-vault-red">Paused</span>
                      ) : a.is_active ? (
                        <span className="text-vault-green">Active</span>
                      ) : (
                        <span className="text-paper-dim">Inactive</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-paper-muted">{formatDate(a.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        )}
      </div>

      {txns.length > 0 && (
        <div>
          <h2 className="mb-3 font-display text-lg font-semibold text-paper">Recent activity</h2>
          <Card className="overflow-x-auto p-0">
            <table className="w-full text-sm">
              <thead className="border-b border-ink-line text-left text-xs uppercase tracking-wider text-paper-dim">
                <tr>
                  <th className="px-4 py-3 font-medium">Amount</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                  <th className="px-4 py-3 font-medium">When</th>
                </tr>
              </thead>
              <tbody>
                {txns.slice(0, 8).map((t) => (
                  <tr key={t.id} className="border-b border-ink-line last:border-0">
                    <td className="px-4 py-3">{formatMicro(t.amount_microalgos)}</td>
                    <td className="px-4 py-3"><StatusBadge status={t.status} /></td>
                    <td className="px-4 py-3 text-paper-muted">{formatDate(t.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        </div>
      )}
    </div>
  );
}
