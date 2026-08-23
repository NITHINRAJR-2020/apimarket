import { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuth, dashboardPathFor } from "../context/AuthContext";
import type { UserRole } from "../types";

/**
 * Guards a route subtree.
 *  - not logged in            -> redirect to /login
 *  - logged in, wrong role    -> redirect to their OWN dashboard
 *  - logged in, allowed role  -> render children
 *
 * This is a UX convenience only. The backend independently enforces every
 * rule; a user who bypasses this guard still gets 401/403/404 from the API.
 */
export default function ProtectedRoute({
  children,
  roles,
}: {
  children: ReactNode;
  roles?: UserRole[];
}) {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center text-paper-muted">
        Loading…
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" state={{ from: location.pathname }} replace />;
  }

  if (roles && !roles.includes(user.role)) {
    // Wrong role for this area — send them to where they belong.
    return <Navigate to={dashboardPathFor(user.role)} replace />;
  }

  return <>{children}</>;
}
