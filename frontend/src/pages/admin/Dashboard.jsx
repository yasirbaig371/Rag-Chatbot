import {
  BookOpen,
  FileText,
  MessageSquare,
  UsersRound,
} from "lucide-react";
import { useEffect, useState } from "react";
import toast from "react-hot-toast";
import { api } from "../../api/client";
import Loader from "../../components/Loader";

const cards = [
  { key: "users", label: "Total users", icon: UsersRound, color: "text-indigo-700 bg-indigo-50" },
  { key: "documents", label: "Documents", icon: FileText, color: "text-purple-700 bg-purple-50" },
  { key: "chat_sessions", label: "Chat sessions", icon: MessageSquare, color: "text-blue-700 bg-blue-50" },
  { key: "chat_messages", label: "Messages", icon: BookOpen, color: "text-emerald-700 bg-emerald-50" },
];

export default function AdminDashboard() {
  const [statistics, setStatistics] = useState(null);
  const [sessions, setSessions] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      api.get("/admin/statistics"),
      api.get("/admin/sessions", { params: { limit: 5 } }),
    ])
      .then(([stats, allSessions]) => {
        setStatistics(stats.data);
        setSessions(allSessions.data);
      })
      .catch((error) => toast.error(error.userMessage || "Could not load admin dashboard."))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <Loader fullPage label="Loading administration..." />;
  return (
    <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
      <p className="text-sm font-semibold text-indigo-600">Administration</p>
      <h1 className="mt-1 text-3xl font-bold text-slate-900">Dashboard</h1>
      <p className="mt-2 text-sm text-slate-500">A quick overview of your chatbot workspace.</p>
      <section className="mt-7 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {cards.map(({ key, label, icon: Icon, color }) => (
          <article className="card flex items-center gap-4" key={key}>
            <span className={`rounded-2xl p-3 ${color}`}><Icon size={22} /></span>
            <div>
              <p className="text-sm text-slate-500">{label}</p>
              <p className="mt-1 text-2xl font-bold text-slate-900">{statistics?.[key] ?? 0}</p>
            </div>
          </article>
        ))}
      </section>
      <section className="mt-5 grid gap-5 lg:grid-cols-2">
        <article className="card">
          <h2 className="font-semibold text-slate-900">Workspace status</h2>
          <dl className="mt-4 grid grid-cols-2 gap-4">
            <div className="rounded-xl bg-slate-50 p-4">
              <dt className="text-xs text-slate-500">Active users</dt>
              <dd className="mt-1 text-xl font-bold text-slate-900">{statistics?.active_users ?? 0}</dd>
            </div>
            <div className="rounded-xl bg-slate-50 p-4">
              <dt className="text-xs text-slate-500">Ready documents</dt>
              <dd className="mt-1 text-xl font-bold text-slate-900">{statistics?.ready_documents ?? 0}</dd>
            </div>
          </dl>
        </article>
        <article className="card">
          <h2 className="font-semibold text-slate-900">Recently active chats</h2>
          {sessions.length === 0 ? (
            <p className="mt-4 text-sm text-slate-500">No chat sessions yet.</p>
          ) : (
            <ul className="mt-3 divide-y divide-slate-100">
              {sessions.map((session) => (
                <li className="flex items-start justify-between gap-4 py-3" key={session.id}>
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-slate-800">{session.title}</p>
                    <p className="mt-1 truncate text-xs text-slate-500">{session.user_email}</p>
                  </div>
                  <span className="shrink-0 text-xs text-slate-400">{session.message_count} messages</span>
                </li>
              ))}
            </ul>
          )}
        </article>
      </section>
    </main>
  );
}
