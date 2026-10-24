import { CalendarDays, MessageSquare, Trash2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import toast from "react-hot-toast";
import { api } from "../../api/client";
import Loader from "../../components/Loader";

export default function History() {
  const [sessions, setSessions] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    const { data } = await api.get("/chat/sessions", { params: { limit: 100 } });
    setSessions(data);
  }, []);

  useEffect(() => {
    load()
      .catch((error) => toast.error(error.userMessage || "Could not load your history."))
      .finally(() => setLoading(false));
  }, [load]);

  async function remove(id) {
    if (!window.confirm("Delete this chat and its messages?")) return;
    try {
      await api.delete(`/chat/sessions/${id}`);
      setSessions((items) => items.filter((session) => session.id !== id));
      toast.success("Chat deleted.");
    } catch (error) {
      toast.error(error.userMessage || "Could not delete this chat.");
    }
  }

  if (loading) return <Loader fullPage label="Loading chat history..." />;
  return (
    <main className="mx-auto max-w-5xl px-4 py-8 sm:px-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-indigo-600">Your workspace</p>
          <h1 className="mt-1 text-3xl font-bold text-slate-900">Chat history</h1>
        </div>
        <Link className="button-primary" to="/chat">Start a chat</Link>
      </div>
      {sessions.length === 0 ? (
        <section className="card mt-8 py-14 text-center">
          <MessageSquare className="mx-auto text-indigo-400" size={30} />
          <h2 className="mt-4 font-semibold text-slate-900">No chats yet. Start a new one!</h2>
          <p className="mt-2 text-sm text-slate-500">Your conversations will appear here.</p>
        </section>
      ) : (
        <ul className="mt-7 grid gap-4 sm:grid-cols-2">
          {sessions.map((session) => (
            <li className="card flex flex-col" key={session.id}>
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <h2 className="truncate font-semibold text-slate-900">{session.title}</h2>
                  <p className="mt-2 truncate text-sm text-indigo-700">
                    {session.document_title || "All accessible documents"}
                  </p>
                </div>
                <button className="icon-button shrink-0" type="button" onClick={() => remove(session.id)} aria-label={`Delete ${session.title}`}>
                  <Trash2 size={17} />
                </button>
              </div>
              <div className="mt-5 flex items-center gap-4 text-xs text-slate-500">
                <span className="inline-flex items-center gap-1"><CalendarDays size={14} />{new Date(session.updated_at).toLocaleDateString()}</span>
                <span className="inline-flex items-center gap-1"><MessageSquare size={14} />{session.message_count} messages</span>
              </div>
              <Link className="button-secondary mt-5 justify-center" to={`/chat?session=${session.id}`}>
                Open conversation
              </Link>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
