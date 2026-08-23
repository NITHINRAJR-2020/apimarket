const STYLES: Record<string, string> = {
  PENDING: "bg-ink-line2 text-paper-muted",
  POLICY_BLOCKED: "bg-vault-red/15 text-vault-red border border-vault-red/40",
  QUOTE_ISSUED: "bg-brass/15 text-brass-bright border border-brass/40",
  PAYMENT_SUBMITTED: "bg-brass/15 text-brass-bright border border-brass/40",
  ESCROW_HELD: "bg-brass/20 text-brass-bright border border-brass/50",
  UPSTREAM_CALLED: "bg-vault-blue/15 text-vault-blue border border-vault-blue/40",
  SERVICE_COMPLETED: "bg-vault-green/15 text-vault-green border border-vault-green/40",
  RELEASED: "bg-vault-green/15 text-vault-green border border-vault-green/40",
  FAILED: "bg-vault-red/15 text-vault-red border border-vault-red/40",
  REFUNDED: "bg-vault-blue/15 text-vault-blue border border-vault-blue/40",
  DISPUTED: "bg-vault-red/20 text-vault-red border border-vault-red/50",
  HELD: "bg-brass/20 text-brass-bright border border-brass/50",
};

export default function StatusBadge({ status }: { status: string }) {
  const style = STYLES[status] ?? "bg-ink-line2 text-paper-muted";
  return (
    <span className={`inline-block rounded px-2 py-0.5 font-mono text-[11px] tracking-wide ${style}`}>
      {status.replace(/_/g, " ")}
    </span>
  );
}
