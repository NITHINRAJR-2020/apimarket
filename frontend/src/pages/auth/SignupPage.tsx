import { FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth, dashboardPathFor } from "../../context/AuthContext";
import { ApiError } from "../../services/api";
import type { UserRole } from "../../types";
import AuthShell from "./AuthShell";
import { Field, inputCls, btnCls } from "./LoginPage";

const ROLE_OPTIONS: { value: Exclude<UserRole, "admin">; title: string; blurb: string }[] = [
  { value: "user", title: "User", blurb: "Run AI agents that buy APIs" },
  { value: "publisher", title: "Publisher", blurb: "Publish APIs and earn from usage" },
];

export default function SignupPage() {
  const { signup } = useAuth();
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [role, setRole] = useState<Exclude<UserRole, "admin">>("user");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    if (password !== confirm) {
      setError("Passwords do not match.");
      return;
    }
    setLoading(true);
    try {
      const user = await signup(name, email, password, role);
      navigate(dashboardPathFor(user.role), { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <AuthShell title="Create your account" subtitle="Choose how you'll use PayperQuery">
      <form onSubmit={handleSubmit} className="space-y-4">
        {error && (
          <div className="rounded-md border border-vault-red/30 bg-vault-red/10 px-3 py-2 text-sm text-vault-red">
            {error}
          </div>
        )}

        <div>
          <span className="mb-1.5 block text-sm font-medium text-paper">I want to join as</span>
          <div className="grid grid-cols-2 gap-3">
            {ROLE_OPTIONS.map((opt) => (
              <button
                type="button"
                key={opt.value}
                onClick={() => setRole(opt.value)}
                className={`rounded-lg border p-3 text-left transition-colors ${
                  role === opt.value
                    ? "border-brass bg-brass/10"
                    : "border-ink-line2 hover:border-ink-line2 hover:bg-ink-panel2"
                }`}
              >
                <div className="text-sm font-semibold text-paper">{opt.title}</div>
                <div className="mt-0.5 text-xs text-paper-dim">{opt.blurb}</div>
              </button>
            ))}
          </div>
        </div>

        <Field label="Full name">
          <input required value={name} onChange={(e) => setName(e.target.value)} className={inputCls} placeholder="Ada Lovelace" />
        </Field>
        <Field label="Email">
          <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} className={inputCls} placeholder="you@example.com" />
        </Field>
        <Field label="Password">
          <input type="password" required value={password} onChange={(e) => setPassword(e.target.value)} className={inputCls} placeholder="At least 8 characters" />
        </Field>
        <Field label="Confirm password">
          <input type="password" required value={confirm} onChange={(e) => setConfirm(e.target.value)} className={inputCls} placeholder="Re-enter your password" />
        </Field>

        <button type="submit" disabled={loading} className={btnCls}>
          {loading ? "Creating account…" : "Create account"}
        </button>
      </form>
      <p className="mt-6 text-center text-sm text-paper-muted">
        Already have an account?{" "}
        <Link to="/login" className="font-medium text-brass-bright hover:underline">
          Sign in
        </Link>
      </p>
    </AuthShell>
  );
}
