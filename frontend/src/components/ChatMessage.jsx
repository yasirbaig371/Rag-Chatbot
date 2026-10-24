import { ChevronDown, ChevronUp, UserRound, Sparkles } from "lucide-react";
import { useState } from "react";

export default function ChatMessage({ message }) {
  const [expanded, setExpanded] = useState(false);
  const isUser = message.role === "user";
  return (
    <article className={`flex gap-3 ${isUser ? "flex-row-reverse" : ""}`}>
      <span className={`mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${isUser ? "bg-indigo-600 text-white" : "bg-purple-100 text-purple-700"}`}>
        {isUser ? <UserRound size={16} /> : <Sparkles size={16} />}
      </span>
      <div className={`max-w-[88%] rounded-2xl px-4 py-3 shadow-sm sm:max-w-[78%] ${isUser ? "bg-gradient-to-r from-indigo-600 to-purple-600 text-white" : "border border-slate-100 bg-white text-slate-800"}`}>
        <p className="whitespace-pre-wrap break-words text-sm leading-6">{message.content}</p>
        {!isUser && message.sources?.length > 0 && (
          <section className="mt-3 border-t border-slate-100 pt-2">
            <button
              type="button"
              className="flex min-h-9 items-center gap-1 text-xs font-semibold text-indigo-700 hover:text-indigo-900 focus:outline-none focus:ring-2 focus:ring-indigo-400"
              onClick={() => setExpanded((value) => !value)}
              aria-expanded={expanded}
            >
              {expanded ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
              Sources ({message.sources.length})
            </button>
            {expanded && (
              <ul className="mt-2 space-y-2">
                {message.sources.map((source) => (
                  <li key={`${source.source_label}-${source.chunk_id}`} className="rounded-lg bg-slate-50 p-3 text-xs text-slate-600">
                    <p className="font-semibold text-slate-800">
                      {source.document_title} · Page {source.page}
                    </p>
                    <p className="mt-1 break-words leading-5">{source.snippet}</p>
                  </li>
                ))}
              </ul>
            )}
          </section>
        )}
      </div>
    </article>
  );
}
