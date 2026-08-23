import { FormEvent, ReactNode, useEffect, useState } from "react";
import { api, ApiError } from "../services/api";
import type { Listing } from "../types";
import { Card } from "../components/Card";
import EmptyState from "../components/EmptyState";
import { formatDate, formatMicro, shortAddr } from "../lib/format";

const emptyForm = {
  name: "",
  description: "",
  category: "general",
  path: "",
  upstream_url: "",
  price_usd: "0.10",
  pay_to_address: "",
  asa_id: "",
};

export default function ListingsPage() {
  const [listings, setListings] = useState<Listing[]>([]);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState(emptyForm);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  async function refresh() {
    setLoading(true);
    const res = await api.listListings(true);
    setListings(res);
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
      await api.createListing({
        name: form.name,
        description: form.description || undefined,
        category: form.category || "general",
        path: form.path,
        upstream_url: form.upstream_url,
        price_microalgos: Math.round(Number(form.price_usd) * 1_000_000),
        pay_to_address: form.pay_to_address,
        asa_id: form.asa_id ? Number(form.asa_id) : null,
      });
      setForm(emptyForm);
      await refresh();
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : "Could not publish this listing");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDeactivate(id: string) {
    await api.deactivateListing(id);
    await refresh();
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-2xl font-semibold text-paper">Listings</h1>
        <p className="mt-1 text-sm text-paper-dim">
          Publish an API to the marketplace. <span className="text-paper">Pay-to address</span> is where you get
          paid on escrow release — agents never see it as the payment destination.
        </p>
      </div>

      <Card>
        <h2 className="font-display text-sm font-semibold text-paper">Publish a new listing</h2>
        <form onSubmit={handleSubmit} className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2">
          <Field label="Name">
            <input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className={inputClass} />
          </Field>
          <Field label="Category">
            <input value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} className={inputClass} />
          </Field>
          <Field label="Marketplace path" hint="the slug agents call: /market/<path>/call">
            <input
              required
              value={form.path}
              onChange={(e) => setForm({ ...form, path: e.target.value })}
              placeholder="weather-berlin"
              className={inputClass}
            />
          </Field>
          <Field label="Price per call (USD)">
            <input
              required
              type="number"
              step="0.01"
              min="0.01"
              value={form.price_usd}
              onChange={(e) => setForm({ ...form, price_usd: e.target.value })}
              className={inputClass}
            />
          </Field>
          <Field label="Upstream URL" hint="the real API this proxies to, only called after escrow is held" className="md:col-span-2">
            <input
              required
              value={form.upstream_url}
              onChange={(e) => setForm({ ...form, upstream_url: e.target.value })}
              placeholder="https://api.example.com/v1/endpoint"
              className={inputClass}
            />
          </Field>
          <Field label="Description" className="md:col-span-2">
            <input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} className={inputClass} />
          </Field>
          <Field label="Pay-to address" hint="your Algorand address, paid from escrow on release">
            <input
              required
              value={form.pay_to_address}
              onChange={(e) => setForm({ ...form, pay_to_address: e.target.value })}
              className={`${inputClass} font-mono`}
            />
          </Field>
          <Field label="ASA ID" hint="leave blank for native ALGO">
            <input value={form.asa_id} onChange={(e) => setForm({ ...form, asa_id: e.target.value })} className={inputClass} />
          </Field>

          <div className="md:col-span-2">
            {formError && <p className="mb-2 text-xs text-vault-red">{formError}</p>}
            <button
              type="submit"
              disabled={submitting}
              className="rounded-md bg-brass px-4 py-2 text-sm font-medium text-ink-bg transition-colors hover:bg-brass-bright disabled:opacity-50"
            >
              {submitting ? "Publishing…" : "Publish listing"}
            </button>
          </div>
        </form>
      </Card>

      <div>
        <h2 className="font-display text-lg font-semibold text-paper">Published listings</h2>
        {loading ? (
          <p className="mt-3 text-sm text-paper-dim">Loading…</p>
        ) : listings.length === 0 ? (
          <div className="mt-3">
            <EmptyState title="No listings yet" hint="Publish your first API above to make it searchable in the marketplace." />
          </div>
        ) : (
          <Card className="mt-3 divide-y divide-ink-line p-0">
            {listings.map((l) => (
              <div key={l.id} className="flex flex-wrap items-center justify-between gap-3 px-5 py-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-display text-sm font-medium text-paper">{l.name}</span>
                    <span className="mono-chip text-[11px] text-paper-dim">/{l.path}</span>
                    {!l.is_active && (
                      <span className="rounded bg-vault-red/15 px-1.5 py-0.5 font-mono text-[10px] text-vault-red">inactive</span>
                    )}
                  </div>
                  <div className="mt-1 text-xs text-paper-dim">
                    pays out to <span className="mono-chip">{shortAddr(l.pay_to_address)}</span> · published{" "}
                    {formatDate(l.created_at)}
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <span className="font-mono text-sm text-paper">{formatMicro(l.price_microalgos)}</span>
                  {l.is_active && (
                    <button
                      onClick={() => handleDeactivate(l.id)}
                      className="rounded-md border border-ink-line2 px-2.5 py-1 text-xs text-paper-muted hover:border-vault-red/50 hover:text-vault-red"
                    >
                      Deactivate
                    </button>
                  )}
                </div>
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
