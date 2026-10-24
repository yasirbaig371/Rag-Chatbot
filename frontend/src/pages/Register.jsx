import { BookOpenCheck, LoaderCircle } from "lucide-react";
import { useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import toast from "react-hot-toast";
import { useAuth } from "../context/AuthContext";

export default function Register() {
  const { user, loading, register } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({
    full_name: "",
    email: "",
    password: "",
    role: "user",
  });
  const [submitting, setSubmitting] = useState(false);
  const [pendingAdminReview, setPendingAdminReview] = useState(false);

  if (!loading && user) {
    return <Navigate to={user.role === "admin" ? "/admin/dashboard" : "/chat"} replace />;
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setSubmitting(true);
    try {
      const account = await register(form);
      if (account.role === "admin" && !account.is_active) {
        setPendingAdminReview(true);
        toast.success("Your administrator request was submitted for review.");
        return;
      }
      toast.success("Your account is ready.");
      navigate(account.role === "admin" ? "/admin/dashboard" : "/chat", { replace: true });
    } catch (error) {
      toast.error(error.userMessage || "Unable to create your account. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  if (pendingAdminReview) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-gradient-to-br from-indigo-50 via-white to-purple-50 px-4 py-12">
        <section className="w-full max-w-md rounded-3xl border border-white bg-white p-8 text-center shadow-card sm:p-10">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-indigo-600 to-purple-600 text-white shadow-lg">
            <BookOpenCheck size={24} />
          </div>
          <h1 className="mt-6 text-2xl font-bold text-slate-900">Request submitted</h1>
          <p className="mt-3 text-sm leading-6 text-slate-600">
            An administrator must review and activate your account before you can sign in. You can close this page while your request is pending.
          </p>
        </section>
      </main>
    );
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-gradient-to-br from-indigo-50 via-white to-purple-50 px-4 py-12">
      <section className="w-full max-w-md rounded-3xl border border-white bg-white p-8 shadow-card sm:p-10">
        <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-indigo-600 to-purple-600 text-white shadow-lg">
          <BookOpenCheck size={24} />
        </div>
        <h1 className="mt-6 text-center text-2xl font-bold text-slate-900">Create your account</h1>
        <p className="mt-2 text-center text-sm text-slate-500">Ask questions across your accessible documents</p>
        <form className="mt-8 space-y-5" onSubmit={handleSubmit}>
          <label className="block text-sm font-medium text-slate-700">
            Full name
            <input className="field mt-2" type="text" autoComplete="name" minLength={2} maxLength={255} required value={form.full_name} onChange={(event) => setForm({ ...form, full_name: event.target.value })} />
          </label>
          <label className="block text-sm font-medium text-slate-700">
            Email address
            <input className="field mt-2" type="email" autoComplete="email" required value={form.email} onChange={(event) => setForm({ ...form, email: event.target.value })} />
          </label>
          <label className="block text-sm font-medium text-slate-700">
            Password
            <input className="field mt-2" type="password" autoComplete="new-password" minLength={8} maxLength={128} required value={form.password} onChange={(event) => setForm({ ...form, password: event.target.value })} />
            <span className="mt-1 block text-xs font-normal text-slate-400">Use at least 8 characters.</span>
          </label>
          <label className="block text-sm font-medium text-slate-700">
            Account role
            <select className="field mt-2" value={form.role} onChange={(event) => setForm({ ...form, role: event.target.value })}>
              <option value="user">User</option>
              <option value="admin">Admin (requires approval)</option>
            </select>
          </label>
          {form.role === "admin" && (
            <p className="text-xs leading-5 text-slate-500">
              Admin requests stay inactive until an existing administrator reviews and activates them.
            </p>
          )}
          <button className="button-primary w-full justify-center" type="submit" disabled={submitting}>
            {submitting && <LoaderCircle size={17} className="animate-spin" />}
            {submitting ? "Creating account..." : "Create account"}
          </button>
        </form>
        <p className="mt-6 text-center text-sm text-slate-500">
          Already registered? <Link className="font-semibold text-indigo-700 hover:underline" to="/login">Sign in</Link>
        </p>
      </section>
    </main>
  );
}
