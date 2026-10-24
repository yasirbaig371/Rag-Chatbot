import { MessageSquarePlus, Trash2 } from "lucide-react";

export default function Sidebar({ sessions, selectedId, onSelect, onNew, onDelete }) {
  return (
    <aside className="flex min-h-0 flex-col border-r border-slate-200 bg-white md:w-72">
      <div className="p-4">
        <button className="button-primary w-full justify-center" onClick={onNew} type="button">
          <MessageSquarePlus size={17} /> New chat
        </button>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-3 pb-4">
        <p className="px-2 pb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">Recent chats</p>
        {sessions.length === 0 ? (
          <p className="px-2 py-5 text-sm text-slate-500">No chats yet. Start a new one!</p>
        ) : (
          <ul className="space-y-1">
            {sessions.map((session) => (
              <li key={session.id}>
                <div className={`group flex items-center rounded-xl ${selectedId === session.id ? "bg-indigo-50" : "hover:bg-slate-50"}`}>
                  <button
                    className={`min-w-0 flex-1 px-3 py-3 text-left text-sm ${selectedId === session.id ? "text-indigo-800" : "text-slate-700"}`}
                    type="button"
                    onClick={() => onSelect(session.id)}
                  >
                    <span className="block truncate font-medium">{session.title}</span>
                    <span className="mt-1 block truncate text-xs text-slate-400">
                      {session.document_title || "All accessible documents"}
                    </span>
                  </button>
                  <button
                    type="button"
                    onClick={() => onDelete(session.id)}
                    className="icon-button mr-1 opacity-70 md:opacity-0 md:group-hover:opacity-100"
                    aria-label={`Delete chat: ${session.title}`}
                    title="Delete chat"
                  >
                    <Trash2 size={15} />
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </aside>
  );
}
