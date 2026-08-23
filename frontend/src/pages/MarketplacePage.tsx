import { FormEvent, useEffect, useState } from "react";
import { api, ApiError } from "../services/api";
import type { ListingSearchResult, QuotePreview } from "../types";
import { Card } from "../components/Card";
import EmptyState from "../components/EmptyState";
import { formatMicro, reputationTone, shortAddr } from "../lib/format";

function ReputationDial({ score }: { score: number }) {
  const tone = reputationTone(score);
  const color = { green: "text-vault-green", brass: "text-brass-bright", red: "text-vault-red" }[tone];
  return (
    <div className={`whitespace-nowrap text-xs font-medium ${color}`}>
      {score}/100 reputation
    </div>
  );
}

function ListingCard({ listing, apiKey }: { listing: ListingSearchResult; apiKey: string }) {
  const [quote, setQuote] = useState<QuotePreview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handlePreview() {
    setError(null);
    setQuote(null);
    if (!apiKey) {
      setError("Enter an agent API key above to preview a quote");
      return;
    }
    setLoading(true);
    try {
      const q = await api.previewQuote(listing.path, apiKey);
      setQuote(q);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not fetch a quote");
    } finally {
      setLoading(false);
    }
  }

  return (
    <Card className="flex flex-col gap-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="font-mono text-[10px] uppercase tracking-widest text-paper-dim">{listing.category}</div>
          <h3 className="font-display text-base font-semibold text-paper">{listing.name}</h3>
        </div>
        <ReputationDial score={listing.reputation_score} />
      </div>

      {listing.description && <p className="text-sm text-paper-muted">{listing.description}</p>}

      <div className="flex items-center justify-between text-xs text-paper-dim">
        <span>
          {listing.successful_transactions} fulfilled · {listing.failed_transactions} failed
        </span>
        <span className="font-mono text-sm text-paper">{formatMicro(listing.price_microalgos)} / call</span>
      </div>

      <div className="mt-1 flex items-center justify-between border-t border-ink-line pt-3">
        <span className="mono-chip text-[11px] text-paper-dim">/market/{listing.path}/call</span>
        <button
          onClick={handlePreview}
          disabled={loading}
          className="rounded-md border border-brass/40 bg-brass/10 px-3 py-1.5 text-xs font-medium text-brass-bright transition-colors hover:bg-brass/20 disabled:opacity-50"
        >
          {loading ? "Fetching…" : "Preview quote"}
        </button>
      </div>

      {error && <p className="text-xs text-vault-red">{error}</p>}

      {quote && (
        <div className="rounded-md border border-ink-line2 bg-ink-panel2 p-3 text-xs">
          <div className="flex justify-between text-paper-dim">
            <span>Pay to (escrow wallet)</span>
            <span className="mono-chip text-brass-bright">{shortAddr(quote.payTo)}</span>
          </div>
          <div className="mt-1 flex justify-between text-paper-dim">
            <span>Amount</span>
            <span className="mono-chip text-paper">{formatMicro(Number(quote.maxAmountRequired))}</span>
          </div>
          <div className="mt-1 flex justify-between text-paper-dim">
            <span>Network</span>
            <span className="mono-chip text-paper">{quote.network}</span>
          </div>
          <p className="mt-2 text-[11px] leading-relaxed text-paper-dim">{quote.note}</p>
        </div>
      )}
    </Card>
  );
}

export default function MarketplacePage() {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("");
  const [minReputation, setMinReputation] = useState(0);
  const [apiKey, setApiKey] = useState("");
  const [results, setResults] = useState<ListingSearchResult[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function runSearch() {
    setLoading(true);
    setError(null);
    try {
      const res = await api.searchMarketplace({ q: query || undefined, category: category || undefined, min_reputation: minReputation || undefined });
      setResults(res);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Search failed");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    runSearch();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    runSearch();
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-2xl font-semibold text-paper">Marketplace</h1>
        <p className="mt-1 text-sm text-paper-dim">
          What an agent searches to find an API worth buying. Every price shown is escrow-backed.
        </p>
      </div>

      <Card>
        <form onSubmit={handleSubmit} className="flex flex-wrap items-end gap-3">
          <div className="flex-1 min-w-[180px]">
            <label className="font-mono text-[10px] uppercase tracking-widest text-paper-dim">Search</label>
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="weather, translation, geocoding…"
              className="mt-1 w-full rounded-md border border-ink-line2 bg-ink-panel2 px-3 py-2 text-sm text-paper outline-none focus:border-brass"
            />
          </div>
          <div className="w-40">
            <label className="font-mono text-[10px] uppercase tracking-widest text-paper-dim">Category</label>
            <input
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              placeholder="any"
              className="mt-1 w-full rounded-md border border-ink-line2 bg-ink-panel2 px-3 py-2 text-sm text-paper outline-none focus:border-brass"
            />
          </div>
          <div className="w-36">
            <label className="font-mono text-[10px] uppercase tracking-widest text-paper-dim">Min reputation</label>
            <input
              type="number"
              min={0}
              max={100}
              value={minReputation}
              onChange={(e) => setMinReputation(Number(e.target.value))}
              className="mt-1 w-full rounded-md border border-ink-line2 bg-ink-panel2 px-3 py-2 text-sm text-paper outline-none focus:border-brass"
            />
          </div>
          <button
            type="submit"
            className="rounded-md bg-brass px-4 py-2 text-sm font-medium text-ink-bg transition-colors hover:bg-brass-bright"
          >
            Search
          </button>
        </form>

        <div className="mt-4 border-t border-ink-line pt-4">
          <label className="font-mono text-[10px] uppercase tracking-widest text-paper-dim">
            Agent API key (to preview quotes)
          </label>
          <input
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder="paste an agent's api_key from the Agents page"
            className="mt-1 w-full rounded-md border border-ink-line2 bg-ink-panel2 px-3 py-2 font-mono text-xs text-paper outline-none focus:border-brass"
          />
        </div>
      </Card>

      {loading ? (
        <p className="text-sm text-paper-dim">Searching…</p>
      ) : error ? (
        <p className="text-sm text-vault-red">{error}</p>
      ) : results.length === 0 ? (
        <EmptyState title="No listings match" hint="Try a broader search, or publish a listing from the Listings page." />
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
          {results.map((listing) => (
            <ListingCard key={listing.id} listing={listing} apiKey={apiKey} />
          ))}
        </div>
      )}
    </div>
  );
}
