import { BookOpenCheck, LogOut, Shield, UserRound } from "lucide-react";
import { Link, NavLink, useNavigate } from "react-router-dom";
import toast from "react-hot-toast";
import { useAuth } from "../context/AuthContext";

const linkClass = ({ isActive }) =>
  `rounded-lg px-3 py-2 text-sm font-medium transition ${
    isActive
      ? "bg-indigo-50 text-indigo-700"
      : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
  }`;

export default function Navbar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  if (!user) return null;

  async function handleLogout() {
    try {
      await logout();
      toast.success("You are signed out.");
      navigate("/login", { replace: true });
    } catch (error) {
      toast.error(error.userMessage || "Signed out locally; server logout could not be confirmed.");
      navigate("/login", { replace: true });
    }
  }

  return (
    <header className="sticky top-0 z-20 border-b border-slate-200 bg-white/90 backdrop-blur">
      <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-4 py-3 sm:px-6">
        <Link to={user.role === "admin" ? "/admin/dashboard" : "/chat"} className="flex items-center gap-2 font-bold text-slate-900">
          <span className="rounded-xl bg-gradient-to-br from-indigo-600 to-purple-600 p-2 text-white">
            <BookOpenCheck size={19} />
          </span>
          <span>Knowledge Desk</span>
        </Link>
        <nav className="flex max-w-[72vw] items-center gap-1 overflow-x-auto whitespace-nowrap" aria-label="Main navigation">
          {user.role === "admin" ? (
            <>
              <NavLink className={linkClass} to="/admin/dashboard">Dashboard</NavLink>
              <NavLink className={linkClass} to="/admin/users">Users</NavLink>
              <NavLink className={linkClass} to="/admin/documents">Documents</NavLink>
              <NavLink className={linkClass} to="/chat">Chat</NavLink>
              <NavLink className={linkClass} to="/history">History</NavLink>
              <NavLink className={linkClass} to="/profile">Profile</NavLink>
            </>
          ) : (
            <>
              <NavLink className={linkClass} to="/chat">Chat</NavLink>
              <NavLink className={linkClass} to="/history">History</NavLink>
              <NavLink className={linkClass} to="/profile">Profile</NavLink>
            </>
          )}
          <span className="ml-2 hidden items-center gap-1 text-xs text-slate-500 sm:flex">
            {user.role === "admin" ? <Shield size={14} /> : <UserRound size={14} />}
            {user.role === "admin" ? "Administrator" : "User"}
          </span>
          <button className="icon-button ml-1" type="button" onClick={handleLogout} aria-label="Sign out" title="Sign out">
            <LogOut size={17} />
          </button>
        </nav>
      </div>
    </header>
  );
}
