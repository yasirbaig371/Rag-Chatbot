import { BookOpenCheck, LoaderCircle } from "lucide-react";
import { useState } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import toast from "react-hot-toast";
import { useAuth } from "../context/AuthContext";

export default function Login() {
  const { user, loading, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [form, setForm] = useState({ email: "", password: "" });
  const [submitting, setSubmitting] = useState(false);

  if (!loading && user) {
    return <Navigate to={user.role === "admin" ? "/admin/dashboard" : "/chat"} replace />;
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setSubmitting(true);
    try {
      const profile = await login(form);
      toast.success("Welcome back.");
      const requestedPath = location.state?.from?.pathname;
      navigate(
        requestedPath || (profile.role === "admin" ? "/admin/dashboard" : "/chat"),
        { replace: true },
      );
    } catch (error) {
      toast.error(error.userMessage || "Unable to sign in. Check your details and try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-gradient-to-br from-indigo-50 via-white to-purple-50 px-4 py-12">
      <section className="w-full max-w-md rounded-3xl border border-white bg-white p-8 shadow-card sm:p-10">
        <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-indigo-600 to-purple-600 text-white shadow-lg">
          <BookOpenCheck size={24} />
        </div>
        <h1 className="mt-6 text-center text-2xl font-bold text-slate-900">Welcome back</h1>
        <p className="mt-2 text-center text-sm text-slate-500">Sign in to your document assistant</p>
        <form className="mt-8 space-y-5" onSubmit={handleSubmit}>
          <label className="block text-sm font-medium text-slate-700">
            Email address
            <input className="field mt-2" type="email" autoComplete="email" required value={form.email} onChange={(event) => setForm({ ...form, email: event.target.value })} />
          </label>
          <label className="block text-sm font-medium text-slate-700">
            Password
            <input className="field mt-2" type="password" autoComplete="current-password" required value={form.password} onChange={(event) => setForm({ ...form, password: event.target.value })} />
          </label>
          <button className="button-primary w-full justify-center" type="submit" disabled={submitting}>
            {submitting && <LoaderCircle size={17} className="animate-spin" />}
            {submitting ? "Signing in..." : "Sign in"}
          </button>
        </form>
        <p className="mt-6 text-center text-sm text-slate-500">
          New to Knowledge Desk? <Link className="font-semibold text-indigo-700 hover:underline" to="/register">Create an account</Link>
        </p>
      </section>
    </main>
  );
}
