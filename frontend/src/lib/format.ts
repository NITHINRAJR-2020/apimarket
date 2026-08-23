export function formatMicro(amount: number | null | undefined): string {
  if (amount == null) return "—";
  return `$${(amount / 1_000_000).toFixed(2)}`;
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function shortAddr(addr: string | null | undefined): string {
  if (!addr) return "—";
  if (addr.length <= 14) return addr;
  return `${addr.slice(0, 6)}…${addr.slice(-6)}`;
}

export function reputationTone(score: number): "green" | "brass" | "red" {
  if (score >= 70) return "green";
  if (score >= 40) return "brass";
  return "red";
}
