import { FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth, dashboardPathFor } from "../../context/AuthContext";
import { ApiError } from "../../services/api";
import AuthShell from "./AuthShell";

export default function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const user = await login(email, password);
      navigate(dashboardPathFor(user.role), { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <AuthShell title="Welcome back" subtitle="Sign in to your PayperQuery account">
      <form onSubmit={handleSubmit} className="space-y-4">
        {error && (
          <div className="rounded-md border border-vault-red/30 bg-vault-red/10 px-3 py-2 text-sm text-vault-red">
            {error}
          </div>
        )}
        <Field label="Email">
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className={inputCls}
            placeholder="you@example.com"
          />
        </Field>
        <Field label="Password">
          <input
            type="password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className={inputCls}
            placeholder="••••••••"
          />
        </Field>
        <button type="submit" disabled={loading} className={btnCls}>
          {loading ? "Signing in…" : "Sign in"}
        </button>
      </form>
      <p className="mt-6 text-center text-sm text-paper-muted">
        Don&apos;t have an account?{" "}
        <Link to="/signup" className="font-medium text-brass-bright hover:underline">
          Create one
        </Link>
      </p>
    </AuthShell>
  );
}

export const inputCls =
  "w-full rounded-md border border-ink-line2 bg-ink-panel px-3 py-2 text-sm text-paper outline-none focus:border-brass focus:ring-1 focus:ring-brass";
export const btnCls =
  "w-full rounded-md bg-brass px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-brass-bright disabled:opacity-60";

export function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-sm font-medium text-paper">{label}</span>
      {children}
    </label>
  );
}
