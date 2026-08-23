import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../services/api";
import type { Listing, Transaction } from "../../types";
import { Card, StatCard } from "../../components/Card";
import EmptyState from "../../components/EmptyState";
import StatusBadge from "../../components/StatusBadge";
import { formatDate, formatMicro } from "../../lib/format";

export default function PublisherDashboard() {
  const [listings, setListings] = useState<Listing[]>([]);
  const [txns, setTxns] = useState<Transaction[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.listListings(true), api.listTransactions()])
      .then(([l, t]) => {
        setListings(l);
        setTxns(t);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <p className="text-paper-muted">Loading…</p>;
  if (error) return <p className="text-vault-red">{error}</p>;

  const active = listings.filter((l) => l.is_active).length;

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-semibold text-paper">Publisher overview</h1>
          <p className="mt-1 text-sm text-paper-muted">Your published APIs and their usage.</p>
        </div>
        <Link to="/publisher/apis" className="rounded-md bg-brass px-4 py-2 text-sm font-semibold text-white hover:bg-brass-bright">
          Manage APIs
        </Link>
      </div>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label="Total APIs" value={listings.length} />
        <StatCard label="Active APIs" value={active} tone="green" />
        <StatCard label="Total requests" value={txns.length} tone="brass" />
        <StatCard label="Inactive" value={listings.length - active} />
      </div>

      <div>
        <h2 className="mb-3 font-display text-lg font-semibold text-paper">My published APIs</h2>
        {listings.length === 0 ? (
          <EmptyState title="You haven't published any APIs yet" hint="Head to My APIs to register your first endpoint." />
        ) : (
          <Card className="overflow-x-auto p-0">
            <table className="w-full text-sm">
              <thead className="border-b border-ink-line text-left text-xs uppercase tracking-wider text-paper-dim">
                <tr>
                  <th className="px-4 py-3 font-medium">Name</th>
                  <th className="px-4 py-3 font-medium">Path</th>
                  <th className="px-4 py-3 font-medium">Price</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                  <th className="px-4 py-3 font-medium">Created</th>
                </tr>
              </thead>
              <tbody>
                {listings.map((l) => (
                  <tr key={l.id} className="border-b border-ink-line last:border-0">
                    <td className="px-4 py-3 font-medium text-paper">{l.name}</td>
                    <td className="px-4 py-3 font-mono text-xs text-paper-muted">/{l.path}</td>
                    <td className="px-4 py-3">{formatMicro(l.price_microalgos)}</td>
                    <td className="px-4 py-3">
                      {l.is_active ? <span className="text-vault-green">Active</span> : <span className="text-paper-dim">Inactive</span>}
                    </td>
                    <td className="px-4 py-3 text-paper-muted">{formatDate(l.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        )}
      </div>

      {txns.length > 0 && (
        <div>
          <h2 className="mb-3 font-display text-lg font-semibold text-paper">Recent usage</h2>
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
