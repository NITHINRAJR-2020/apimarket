import { FormEvent, ReactNode, useEffect, useState } from "react";
import { api, ApiError } from "../services/api";
import type { Agent } from "../types";
import { Card } from "../components/Card";
import EmptyState from "../components/EmptyState";
import { formatDate, shortAddr } from "../lib/format";

const emptyForm = {
  name: "",
  wallet_address: "",
  max_transaction_amount: "5.00",
  daily_limit: "50.00",
  min_provider_reputation: "40",
};

export default function AgentsPage() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState(emptyForm);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [revealedKey, setRevealedKey] = useState<string | null>(null);

  async function refresh() {
    setLoading(true);
    setAgents(await api.listAgents());
    setLoading(false);
  }

  useEffect(() => {
    refresh();
  }, []);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setFormError(null);
    setSubmitting(true);
    try {
      const agent = await api.createAgent({
        name: form.name,
        wallet_address: form.wallet_address,
        policy: {
          max_transaction_amount: form.max_transaction_amount,
          daily_limit: form.daily_limit,
          min_provider_reputation: Number(form.min_provider_reputation),
          restrict_to_allowed_listings: false,
        },
      });
      setRevealedKey(agent.api_key);
      setForm(emptyForm);
      await refresh();
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : "Could not register this agent");
    } finally {
      setSubmitting(false);
    }
  }

  async function togglePause(agent: Agent) {
    await api.setAgentPaused(agent.id, !agent.is_paused);
    await refresh();
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-2xl font-semibold text-paper">Agents</h1>
        <p className="mt-1 text-sm text-paper-dim">
          Register a spending policy before an agent can buy anything. Every purchase is checked against it before
          any payment is requested.
        </p>
      </div>

      <Card>
        <h2 className="font-display text-sm font-semibold text-paper">Register a new agent</h2>
        <form onSubmit={handleSubmit} className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2">
          <Field label="Name">
            <input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className={inputClass} />
          </Field>
          <Field label="Wallet address" hint="the agent's own Algorand address">
            <input
              required
              value={form.wallet_address}
              onChange={(e) => setForm({ ...form, wallet_address: e.target.value })}
              className={`${inputClass} font-mono`}
            />
          </Field>
          <Field label="Max per transaction (USD)">
            <input
              required
              type="number"
              step="0.01"
              value={form.max_transaction_amount}
              onChange={(e) => setForm({ ...form, max_transaction_amount: e.target.value })}
              className={inputClass}
            />
          </Field>
          <Field label="Daily limit (USD)">
            <input
              required
              type="number"
              step="0.01"
              value={form.daily_limit}
              onChange={(e) => setForm({ ...form, daily_limit: e.target.value })}
              className={inputClass}
            />
          </Field>
          <Field label="Minimum provider reputation" hint="0–100, blocks purchases below the bar" className="md:col-span-2">
            <input
              type="number"
              min={0}
              max={100}
              value={form.min_provider_reputation}
              onChange={(e) => setForm({ ...form, min_provider_reputation: e.target.value })}
              className={inputClass}
            />
          </Field>
          <div className="md:col-span-2">
            {formError && <p className="mb-2 text-xs text-vault-red">{formError}</p>}
            <button
              type="submit"
              disabled={submitting}
              className="rounded-md bg-brass px-4 py-2 text-sm font-medium text-ink-bg transition-colors hover:bg-brass-bright disabled:opacity-50"
            >
              {submitting ? "Registering…" : "Register agent"}
            </button>
          </div>
        </form>

        {revealedKey && (
          <div className="mt-4 rounded-md border border-brass/40 bg-brass/10 p-3">
            <p className="font-mono text-[11px] uppercase tracking-widest text-brass-bright">
              API key — shown once, save it now
            </p>
            <p className="mono-chip mt-1 select-all text-sm text-paper">{revealedKey}</p>
          </div>
        )}
      </Card>

      <div>
        <h2 className="font-display text-lg font-semibold text-paper">Registered agents</h2>
        {loading ? (
          <p className="mt-3 text-sm text-paper-dim">Loading…</p>
        ) : agents.length === 0 ? (
          <div className="mt-3">
            <EmptyState title="No agents yet" hint="Register one above to give it a wallet, a policy, and an API key." />
          </div>
        ) : (
          <Card className="mt-3 divide-y divide-ink-line p-0">
            {agents.map((a) => (
              <div key={a.id} className="flex flex-wrap items-center justify-between gap-3 px-5 py-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-display text-sm font-medium text-paper">{a.name}</span>
                    {a.is_paused && (
                      <span className="rounded bg-vault-red/15 px-1.5 py-0.5 font-mono text-[10px] text-vault-red">paused</span>
                    )}
                  </div>
                  <div className="mt-1 text-xs text-paper-dim">
                    <span className="mono-chip">{shortAddr(a.wallet_address)}</span> · registered {formatDate(a.created_at)}
                    {a.policy && (
                      <>
                        {" "}
                        · max ${a.policy.max_transaction_amount}/tx · ${a.policy.daily_limit}/day
                      </>
                    )}
                  </div>
                </div>
                <button
                  onClick={() => togglePause(a)}
                  className={`rounded-md border px-2.5 py-1 text-xs transition-colors ${
                    a.is_paused
                      ? "border-vault-green/40 text-vault-green hover:bg-vault-green/10"
                      : "border-ink-line2 text-paper-muted hover:border-vault-red/50 hover:text-vault-red"
                  }`}
                >
                  {a.is_paused ? "Resume" : "Pause"}
                </button>
              </div>
            ))}
          </Card>
        )}
      </div>
    </div>
  );
}

const inputClass =
  "mt-1 w-full rounded-md border border-ink-line2 bg-ink-panel2 px-3 py-2 text-sm text-paper outline-none focus:border-brass";

function Field({
  label,
  hint,
  children,
  className = "",
}: {
  label: string;
  hint?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={className}>
      <label className="font-mono text-[10px] uppercase tracking-widest text-paper-dim">{label}</label>
      {children}
      {hint && <p className="mt-1 text-[11px] text-paper-dim">{hint}</p>}
    </div>
  );
}
