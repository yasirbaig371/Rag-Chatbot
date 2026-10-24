import { ChevronLeft, ChevronRight, Search, Trash2, UserCheck, UserX } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import toast from "react-hot-toast";
import { api } from "../../api/client";
import Loader from "../../components/Loader";

export default function AdminUsers() {
  const [users, setUsers] = useState([]);
  const [newUser, setNewUser] = useState({ full_name: "", email: "", password: "", role: "user" });
  const [creating, setCreating] = useState(false);
  const [search, setSearch] = useState("");
  const [role, setRole] = useState("");
  const [active, setActive] = useState("");
  const [limit] = useState(10);
  const [offset, setOffset] = useState(0);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = { limit, offset };
      if (search.trim()) params.search = search.trim();
      if (role) params.role = role;
      if (active) params.is_active = active;
      const { data } = await api.get("/admin/users", { params });
      setUsers(data.items);
      setTotal(data.total);
    } catch (error) {
      toast.error(error.userMessage || "Could not load users.");
    } finally {
      setLoading(false);
    }
  }, [active, limit, offset, role, search]);

  useEffect(() => {
    const timer = window.setTimeout(load, 250);
    return () => window.clearTimeout(timer);
  }, [load]);

  async function updateUser(id, action, value) {
    try {
      const path = action === "role" ? "role" : "status";
      await api.patch(`/admin/users/${id}/${path}`, action === "role" ? { role: value } : { is_active: value });
      toast.success("User updated.");
      await load();
    } catch (error) {
      toast.error(error.userMessage || "Could not update this user.");
    }
  }

  async function deleteUser(user) {
    if (!window.confirm(`Delete ${user.full_name}'s account, uploaded PDFs, and chat history? This cannot be undone.`)) return;
    try {
      await api.delete(`/admin/users/${user.id}`);
      toast.success("User and associated data deleted.");
      await load();
    } catch (error) {
      toast.error(error.userMessage || "Could not delete this user.");
    }
  }

  async function createUser(event) {
    event.preventDefault();
    setCreating(true);
    try {
      const { data } = await api.post("/admin/users", newUser);
      toast.success(`${data.role === "admin" ? "Administrator" : "User"} account created.`);
      setNewUser({ full_name: "", email: "", password: "", role: "user" });
      setOffset(0);
      await load();
    } catch (error) {
      toast.error(error.userMessage || "Could not create this account.");
    } finally {
      setCreating(false);
    }
  }

  return (
    <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
      <p className="text-sm font-semibold text-indigo-600">Administration</p>
      <h1 className="mt-1 text-3xl font-bold text-slate-900">Users</h1>
      <p className="mt-2 text-sm text-slate-500">Search and manage access. Inactive admin accounts may be awaiting approval; activate only after verifying the request. The last active administrator cannot be removed or disabled.</p>
      <section className="card mt-7">
        <h2 className="text-lg font-semibold text-slate-900">Create an account</h2>
        <p className="mt-1 text-sm text-slate-500">Choose whether the new account should be a user or administrator.</p>
        <form className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-5" onSubmit={createUser}>
          <label className="text-sm font-medium text-slate-700">
            Full name
            <input className="field mt-2" type="text" autoComplete="name" minLength={2} maxLength={255} required value={newUser.full_name} onChange={(event) => setNewUser({ ...newUser, full_name: event.target.value })} />
          </label>
          <label className="text-sm font-medium text-slate-700">
            Email address
            <input className="field mt-2" type="email" autoComplete="email" required value={newUser.email} onChange={(event) => setNewUser({ ...newUser, email: event.target.value })} />
          </label>
          <label className="text-sm font-medium text-slate-700">
            Initial password
            <input className="field mt-2" type="password" autoComplete="new-password" minLength={8} maxLength={128} required value={newUser.password} onChange={(event) => setNewUser({ ...newUser, password: event.target.value })} />
          </label>
          <label className="text-sm font-medium text-slate-700">
            Role
            <select className="field mt-2" value={newUser.role} onChange={(event) => setNewUser({ ...newUser, role: event.target.value })}>
              <option value="user">User</option>
              <option value="admin">Admin</option>
            </select>
          </label>
          <div className="flex items-end">
            <button className="button-primary w-full justify-center" type="submit" disabled={creating}>
              {creating ? "Creating..." : "Create account"}
            </button>
          </div>
        </form>
      </section>
      <section className="card mt-7">
        <div className="grid gap-3 sm:grid-cols-[minmax(220px,1fr)_160px_160px]">
          <label className="relative">
            <span className="sr-only">Search users</span>
            <Search className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={17} />
            <input className="field pl-10" placeholder="Search by name or email" value={search} onChange={(event) => { setSearch(event.target.value); setOffset(0); }} />
          </label>
          <label className="sr-only" htmlFor="role-filter">Filter by role</label>
          <select id="role-filter" className="field" value={role} onChange={(event) => { setRole(event.target.value); setOffset(0); }}>
            <option value="">All roles</option>
            <option value="user">User</option>
            <option value="admin">Admin</option>
          </select>
          <label className="sr-only" htmlFor="status-filter">Filter by status</label>
          <select id="status-filter" className="field" value={active} onChange={(event) => { setActive(event.target.value); setOffset(0); }}>
            <option value="">All statuses</option>
            <option value="true">Active</option>
            <option value="false">Inactive</option>
          </select>
        </div>
        {loading ? <Loader label="Loading users..." /> : users.length === 0 ? (
          <p className="py-12 text-center text-sm text-slate-500">No users match these filters.</p>
        ) : (
          <div className="mt-5 overflow-x-auto">
            <table className="w-full min-w-[760px] text-left text-sm">
              <thead className="border-b border-slate-100 text-xs uppercase tracking-wide text-slate-400">
                <tr><th className="px-3 py-3">User</th><th className="px-3 py-3">Role</th><th className="px-3 py-3">Status</th><th className="px-3 py-3">Joined</th><th className="px-3 py-3 text-right">Actions</th></tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {users.map((user) => (
                  <tr key={user.id}>
                    <td className="px-3 py-4">
                      <p className="font-medium text-slate-800">{user.full_name}</p>
                      <p className="mt-1 text-xs text-slate-500">{user.email}</p>
                    </td>
                    <td className="px-3 py-4">
                      <label className="sr-only" htmlFor={`role-${user.id}`}>Role for {user.email}</label>
                      <select id={`role-${user.id}`} className="field max-w-32 py-2 text-xs" value={user.role} onChange={(event) => updateUser(user.id, "role", event.target.value)}>
                        <option value="user">User</option><option value="admin">Admin</option>
                      </select>
                    </td>
                    <td className="px-3 py-4">
                      <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${user.is_active ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-500"}`}>
                        {user.is_active ? "Active" : "Inactive"}
                      </span>
                    </td>
                    <td className="px-3 py-4 text-xs text-slate-500">{new Date(user.created_at).toLocaleDateString()}</td>
                    <td className="px-3 py-4">
                      <div className="flex justify-end gap-1">
                        <button type="button" className="icon-button" onClick={() => updateUser(user.id, "status", !user.is_active)} aria-label={`${user.is_active ? "Deactivate" : "Activate"} ${user.email}`}>
                          {user.is_active ? <UserX size={17} /> : <UserCheck size={17} />}
                        </button>
                        <button type="button" className="icon-button hover:!text-rose-600" onClick={() => deleteUser(user)} aria-label={`Delete ${user.email}`}>
                          <Trash2 size={17} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="mt-4 flex items-center justify-between border-t border-slate-100 pt-4 text-xs text-slate-500">
          <span>{total === 0 ? "0 users" : `${offset + 1}–${Math.min(offset + users.length, total)} of ${total}`}</span>
          <div className="flex gap-1">
            <button className="icon-button" type="button" disabled={offset === 0} onClick={() => setOffset((value) => Math.max(0, value - limit))} aria-label="Previous page"><ChevronLeft size={18} /></button>
            <button className="icon-button" type="button" disabled={offset + limit >= total} onClick={() => setOffset((value) => value + limit)} aria-label="Next page"><ChevronRight size={18} /></button>
          </div>
        </div>
      </section>
    </main>
  );
}
