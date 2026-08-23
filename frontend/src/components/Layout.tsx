import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import ChatWidget from "./ChatWidget";
import type { UserRole } from "../types";

interface NavItem {
  to: string;
  label: string;
  end?: boolean;
}

const NAV_BY_ROLE: Record<UserRole, NavItem[]> = {
  admin: [
    { to: "/admin", label: "Overview", end: true },
    { to: "/admin/users", label: "Users" },
    { to: "/admin/apis", label: "APIs" },
    { to: "/admin/agents", label: "Agents" },
    { to: "/admin/transactions", label: "Transactions" },
    { to: "/admin/escrow", label: "Escrow" },
  ],
  publisher: [
    { to: "/publisher", label: "Overview", end: true },
    { to: "/publisher/apis", label: "My APIs" },
    { to: "/publisher/transactions", label: "Usage" },
    { to: "/publisher/marketplace", label: "Marketplace" },
  ],
  user: [
    { to: "/user", label: "Overview", end: true },
    { to: "/user/agents", label: "My Agents" },
    { to: "/user/marketplace", label: "Marketplace" },
    { to: "/user/transactions", label: "Activity" },
  ],
};

const ROLE_LABEL: Record<UserRole, string> = {
  admin: "Admin",
  publisher: "Publisher",
  user: "User",
};

export default function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  if (!user) return null;
  const items = NAV_BY_ROLE[user.role];

  function handleLogout() {
    logout();
    navigate("/login", { replace: true });
  }

  return (
    <div className="min-h-screen bg-ink-bg text-paper">
      <div className="flex">
        {/* Sidebar */}
        <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col border-r border-ink-line bg-ink-panel md:flex">
          <div className="flex items-center gap-2 px-5 py-5">
            <span className="font-display text-lg font-semibold tracking-tight">PayperQuery</span>
          </div>
          <div className="px-5 pb-3">
            <span className="inline-flex items-center rounded-full bg-brass/15 px-2.5 py-0.5 text-xs font-medium text-brass-bright">
              {ROLE_LABEL[user.role]}
            </span>
          </div>
          <nav className="flex flex-1 flex-col gap-1 px-3 py-2">
            {items.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  `rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                    isActive
                      ? "bg-brass/15 text-brass-bright"
                      : "text-paper-muted hover:bg-ink-panel2 hover:text-paper"
                  }`
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
          <div className="border-t border-ink-line px-4 py-4">
            <div className="mb-2 truncate text-sm font-medium text-paper">{user.name}</div>
            <div className="mb-3 truncate text-xs text-paper-dim">{user.email}</div>
            <button
              onClick={handleLogout}
              className="w-full rounded-md border border-ink-line2 px-3 py-1.5 text-sm text-paper-muted transition-colors hover:bg-ink-panel2 hover:text-paper"
            >
              Log out
            </button>
          </div>
        </aside>

        {/* Main column */}
        <div className="flex min-h-screen w-full flex-col">
          {/* Mobile top bar */}
          <header className="flex items-center justify-between border-b border-ink-line bg-ink-panel px-5 py-3 md:hidden">
            <span className="font-display font-semibold">PayperQuery</span>
            <button onClick={handleLogout} className="text-sm text-paper-muted">
              Log out
            </button>
          </header>
          {/* Mobile nav */}
          <nav className="flex gap-1 overflow-x-auto border-b border-ink-line bg-ink-panel px-3 py-2 md:hidden">
            {items.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  `whitespace-nowrap rounded-md px-3 py-1.5 text-sm font-medium ${
                    isActive ? "bg-brass/15 text-brass-bright" : "text-paper-muted"
                  }`
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>

          <main className="mx-auto w-full max-w-6xl flex-1 px-6 py-8">
            <Outlet />
          </main>
        </div>
      </div>
      <ChatWidget />
    </div>
  );
}
