import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth, dashboardPathFor } from "./context/AuthContext";
import ProtectedRoute from "./components/ProtectedRoute";
import Layout from "./components/Layout";

import LoginPage from "./pages/auth/LoginPage";
import SignupPage from "./pages/auth/SignupPage";

import AdminDashboard from "./pages/admin/AdminDashboard";
import AdminUsers from "./pages/admin/AdminUsers";
import PublisherDashboard from "./pages/publisher/PublisherDashboard";
import UserDashboard from "./pages/user/UserDashboard";

// Reused feature pages (now behind auth + role scoping):
import ListingsPage from "./pages/ListingsPage";
import AgentsPage from "./pages/AgentsPage";
import MarketplacePage from "./pages/MarketplacePage";
import TransactionsPage from "./pages/TransactionsPage";
import EscrowPage from "./pages/EscrowPage";

/** Sends "/" to the right dashboard, or to /login if signed out. */
function RootRedirect() {
  const { user, loading } = useAuth();
  if (loading) return null;
  return <Navigate to={user ? dashboardPathFor(user.role) : "/login"} replace />;
}

export default function App() {
  return (
    <Routes>
      {/* Public */}
      <Route path="/login" element={<LoginPage />} />
      <Route path="/signup" element={<SignupPage />} />

      {/* Admin area */}
      <Route
        element={
          <ProtectedRoute roles={["admin"]}>
            <Layout />
          </ProtectedRoute>
        }
      >
        <Route path="/admin" element={<AdminDashboard />} />
        <Route path="/admin/users" element={<AdminUsers />} />
        <Route path="/admin/apis" element={<ListingsPage />} />
        <Route path="/admin/agents" element={<AgentsPage />} />
        <Route path="/admin/transactions" element={<TransactionsPage />} />
        <Route path="/admin/escrow" element={<EscrowPage />} />
      </Route>

      {/* Publisher area */}
      <Route
        element={
          <ProtectedRoute roles={["publisher"]}>
            <Layout />
          </ProtectedRoute>
        }
      >
        <Route path="/publisher" element={<PublisherDashboard />} />
        <Route path="/publisher/apis" element={<ListingsPage />} />
        <Route path="/publisher/transactions" element={<TransactionsPage />} />
        <Route path="/publisher/marketplace" element={<MarketplacePage />} />
      </Route>

      {/* User area */}
      <Route
        element={
          <ProtectedRoute roles={["user"]}>
            <Layout />
          </ProtectedRoute>
        }
      >
        <Route path="/user" element={<UserDashboard />} />
        <Route path="/user/agents" element={<AgentsPage />} />
        <Route path="/user/marketplace" element={<MarketplacePage />} />
        <Route path="/user/transactions" element={<TransactionsPage />} />
      </Route>

      {/* Fallbacks */}
      <Route path="/" element={<RootRedirect />} />
      <Route path="*" element={<RootRedirect />} />
    </Routes>
  );
}
