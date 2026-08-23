import { useEffect, useState } from "react";
import { api } from "../../services/api";
import type { User, UserRole } from "../../types";
import { Card } from "../../components/Card";
import EmptyState from "../../components/EmptyState";
import { useAuth } from "../../context/AuthContext";
import { formatDate } from "../../lib/format";

const ROLES: UserRole[] = ["user", "publisher", "admin"];

const roleBadge: Record<UserRole, string> = {
  admin: "bg-vault-blue/15 text-vault-blue",
  publisher: "bg-brass/15 text-brass-bright",
  user: "bg-ink-panel2 text-paper-muted",
};

export default function AdminUsers() {
  const { user: me } = useAuth();
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  async function refresh() {
    setLoading(true);
    try {
      setUsers(await api.adminListUsers());
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  async function changeRole(u: User, role: UserRole) {
    if (role === u.role) return;
    setBusy(u.id);
    try {
      const updated = await api.adminSetUserRole(u.id, role);
      setUsers((prev) => prev.map((x) => (x.id === u.id ? updated : x)));
    } catch (e) {
      alert((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  async function toggleStatus(u: User) {
    const disabling = u.is_active;
    if (disabling && !confirm(`Disable ${u.email}? They will be logged out and blocked from the API.`)) {
      return;
    }
    setBusy(u.id);
    try {
      const updated = await api.adminSetUserStatus(u.id, !u.is_active);
      setUsers((prev) => prev.map((x) => (x.id === u.id ? updated : x)));
    } catch (e) {
      alert((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  if (loading) return <p className="text-paper-muted">Loading…</p>;
  if (error) return <p className="text-vault-red">{error}</p>;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-2xl font-semibold text-paper">Users</h1>
        <p className="mt-1 text-sm text-paper-muted">Manage roles and account access.</p>
      </div>

      {users.length === 0 ? (
        <EmptyState title="No users yet" />
      ) : (
        <Card className="overflow-x-auto p-0">
          <table className="w-full text-sm">
            <thead className="border-b border-ink-line text-left text-xs uppercase tracking-wider text-paper-dim">
              <tr>
                <th className="px-4 py-3 font-medium">Name</th>
                <th className="px-4 py-3 font-medium">Email</th>
                <th className="px-4 py-3 font-medium">Role</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium">Joined</th>
                <th className="px-4 py-3 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => {
                const isSelf = u.id === me?.id;
                return (
                  <tr key={u.id} className="border-b border-ink-line last:border-0">
                    <td className="px-4 py-3 font-medium text-paper">
                      {u.name} {isSelf && <span className="text-xs text-paper-dim">(you)</span>}
                    </td>
                    <td className="px-4 py-3 text-paper-muted">{u.email}</td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${roleBadge[u.role]}`}>
                        {u.role}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      {u.is_active ? (
                        <span className="text-vault-green">Active</span>
                      ) : (
                        <span className="text-vault-red">Disabled</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-paper-muted">{formatDate(u.created_at)}</td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <select
                          value={u.role}
                          disabled={busy === u.id || isSelf}
                          onChange={(e) => changeRole(u, e.target.value as UserRole)}
                          className="rounded-md border border-ink-line2 bg-ink-panel px-2 py-1 text-xs disabled:opacity-50"
                        >
                          {ROLES.map((r) => (
                            <option key={r} value={r}>
                              {r}
                            </option>
                          ))}
                        </select>
                        <button
                          disabled={busy === u.id || isSelf}
                          onClick={() => toggleStatus(u)}
                          className="rounded-md border border-ink-line2 px-2 py-1 text-xs text-paper-muted transition-colors hover:bg-ink-panel2 disabled:opacity-50"
                        >
                          {u.is_active ? "Disable" : "Enable"}
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
