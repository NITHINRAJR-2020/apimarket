import type { EscrowStatus } from "../types";

function AddressChip({ label, txId }: { label: string; txId: string | null | undefined }) {
  if (!txId) return null;
  const short = txId.length > 14 ? `${txId.slice(0, 6)}…${txId.slice(-6)}` : txId;
  return (
    <button
      title={`${label}: ${txId} (click to copy)`}
      onClick={() => navigator.clipboard?.writeText(txId)}
      className="mono-chip rounded border border-ink-line2 bg-ink-panel2 px-1.5 py-0.5 text-[10px] text-paper-muted hover:border-brass/50 hover:text-brass-bright"
    >
      {short}
    </button>
  );
}

/**
 * The escrow custody chain, rendered like a ledger stamp trail: three
 * waypoints (Deposit -> Held -> Outcome), each lit up once its on-chain
 * transaction exists. This is the one place in the UI where the
 * distinction this project makes -- funds sit in PLATFORM custody between
 * payment and delivery -- is made visually unmissable.
 */
export default function LedgerTracker({
  status,
  depositTxId,
  payoutTxId,
  refundTxId,
}: {
  status: EscrowStatus | "PENDING";
  depositTxId?: string | null;
  payoutTxId?: string | null;
  refundTxId?: string | null;
}) {
  const held = Boolean(depositTxId);
  const resolved = status === "RELEASED" || status === "REFUNDED";
  const disputed = status === "DISPUTED";

  const outcomeLabel =
    status === "RELEASED" ? "Released to provider" : status === "REFUNDED" ? "Refunded to agent" : disputed ? "Disputed" : "Awaiting outcome";

  const TONE_CLASSES: Record<string, { dot: string; line: string }> = {
    brass: { dot: "border-brass bg-brass", line: "bg-brass/50" },
    "vault-green": { dot: "border-vault-green bg-vault-green", line: "bg-vault-green/50" },
    "vault-blue": { dot: "border-vault-blue bg-vault-blue", line: "bg-vault-blue/50" },
    "vault-red": { dot: "border-vault-red bg-vault-red", line: "bg-vault-red/50" },
    "ink-line2": { dot: "border-ink-line2 bg-ink-line2", line: "bg-ink-line2" },
  };

  const outcomeToneKey = status === "RELEASED" ? "vault-green" : status === "REFUNDED" ? "vault-blue" : disputed ? "vault-red" : "ink-line2";

  const Node = ({ lit, label, toneKey }: { lit: boolean; label: string; toneKey: string }) => (
    <div className="flex flex-col items-center gap-1">
      <div
        className={`h-2.5 w-2.5 rounded-full border ${
          lit ? TONE_CLASSES[toneKey].dot : "border-ink-line2 bg-ink-panel2"
        }`}
      />
      <span className={`font-mono text-[10px] uppercase tracking-wider ${lit ? "text-paper" : "text-paper-dim"}`}>
        {label}
      </span>
    </div>
  );

  return (
    <div className="flex items-center gap-2">
      <Node lit={held} label="Deposit" toneKey="brass" />
      <AddressChip label="Deposit" txId={depositTxId} />
      <div className={`h-px w-6 ${held ? "bg-brass/50" : "bg-ink-line2"}`} />
      <Node lit={held} label="Held" toneKey="brass" />
      <div className={`h-px w-6 ${resolved || disputed ? "bg-brass/50" : "bg-ink-line2"}`} />
      <Node lit={resolved || disputed} label={outcomeLabel} toneKey={outcomeToneKey} />
      <AddressChip label="Payout" txId={payoutTxId} />
      <AddressChip label="Refund" txId={refundTxId} />
    </div>
  );
}
