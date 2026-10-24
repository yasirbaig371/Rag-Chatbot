import { ArrowUp, MessageCircle, Plus, Send, Sparkles } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import toast from "react-hot-toast";
import { api } from "../../api/client";
import ChatMessage from "../../components/ChatMessage";
import Loader from "../../components/Loader";
import Sidebar from "../../components/Sidebar";

export default function Chat() {
  const [searchParams] = useSearchParams();
  const [sessions, setSessions] = useState([]);
  const [documents, setDocuments] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [activeSession, setActiveSession] = useState(null);
  const [scopeDocumentId, setScopeDocumentId] = useState("");
  const [draft, setDraft] = useState("");
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const messagesEnd = useRef(null);

  const loadSessions = useCallback(async () => {
    const { data } = await api.get("/chat/sessions", { params: { limit: 50 } });
    setSessions(data);
  }, []);

  const loadDocuments = useCallback(async () => {
    const { data } = await api.get("/documents", { params: { limit: 500 } });
    setDocuments(data.filter((item) => item.status === "ready"));
  }, []);

  useEffect(() => {
    let active = true;
    Promise.all([loadSessions(), loadDocuments()])
      .catch((error) => toast.error(error.userMessage || "Could not load your chats and documents."))
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [loadDocuments, loadSessions]);

  useEffect(() => {
    const sessionId = Number(searchParams.get("session"));
    if (sessionId > 0) selectSession(sessionId);
  }, [searchParams]);

  useEffect(() => {
    messagesEnd.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [activeSession?.messages, sending]);

  const scopeLabel = useMemo(() => {
    if (!activeSession) {
      return documents.find((doc) => String(doc.id) === scopeDocumentId)?.title ||
        "All accessible documents";
    }
    return activeSession.document_title || "All accessible documents";
  }, [activeSession, documents, scopeDocumentId]);

  async function selectSession(id) {
    try {
      const { data } = await api.get(`/chat/sessions/${id}`);
      setSelectedId(id);
      setActiveSession(data);
      setDraft("");
    } catch (error) {
      toast.error(error.userMessage || "This chat could not be opened.");
    }
  }

  async function startNewChat() {
    try {
      const payload = scopeDocumentId
        ? { document_id: Number(scopeDocumentId) }
        : {};
      const { data } = await api.post("/chat/sessions", payload);
      setSelectedId(data.id);
      setActiveSession(data);
      setDraft("");
      await loadSessions();
    } catch (error) {
      toast.error(error.userMessage || "Could not start a new chat.");
    }
  }

  async function deleteSession(id) {
    if (!window.confirm("Delete this chat and its messages?")) return;
    try {
      await api.delete(`/chat/sessions/${id}`);
      if (selectedId === id) {
        setSelectedId(null);
        setActiveSession(null);
      }
      await loadSessions();
      toast.success("Chat deleted.");
    } catch (error) {
      toast.error(error.userMessage || "Could not delete this chat.");
    }
  }

  async function sendMessage(event) {
    event?.preventDefault();
    const content = draft.trim();
    if (!content || sending) return;
    let session = activeSession;
    if (!session) {
      try {
        const payload = scopeDocumentId
          ? { document_id: Number(scopeDocumentId) }
          : {};
        const created = await api.post("/chat/sessions", payload);
        session = created.data;
        setSelectedId(session.id);
        setActiveSession(session);
      } catch (error) {
        toast.error(error.userMessage || "Could not start a chat.");
        return;
      }
    }

    setSending(true);
    try {
      const { data } = await api.post(
        `/chat/sessions/${session.id}/messages`,
        { content },
      );
      setActiveSession((current) => ({
        ...session,
        ...current,
        title: current?.title === "New Chat" ? content.slice(0, 255) : current?.title || session.title,
        messages: [
          ...(current?.messages || []),
          data.user_message,
          data.assistant_message,
        ],
      }));
      setDraft("");
      await loadSessions();
    } catch (error) {
      toast.error(`${error.userMessage || "The answer could not be generated."} Your draft is still here; please retry.`);
    } finally {
      setSending(false);
    }
  }

  function handleKeyDown(event) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      sendMessage();
    }
  }

  if (loading) return <Loader fullPage label="Loading your workspace..." />;

  return (
    <main className="mx-auto flex h-[calc(100vh-65px)] max-w-7xl overflow-hidden bg-slate-50 md:my-4 md:h-[calc(100vh-97px)] md:rounded-2xl md:border md:border-slate-200 md:shadow-card">
      <div className="hidden min-h-0 md:flex">
        <Sidebar
          sessions={sessions}
          selectedId={selectedId}
          onSelect={selectSession}
          onNew={startNewChat}
          onDelete={deleteSession}
        />
      </div>
      <section className="flex min-w-0 flex-1 flex-col">
        <header className="border-b border-slate-200 bg-white px-4 py-3 sm:px-6">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="min-w-0">
              <h1 className="truncate font-semibold text-slate-900">
                {activeSession?.title || "Ask your documents"}
              </h1>
              <p className="mt-1 truncate text-xs text-slate-500">
                Searching: <span className="font-medium text-indigo-700">{scopeLabel}</span>
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {sessions.length > 0 && (
                <>
                  <label className="sr-only" htmlFor="mobile-chat-select">Choose a chat</label>
                  <select
                    id="mobile-chat-select"
                    className="field max-w-[150px] py-2 text-xs md:hidden"
                    value={selectedId || ""}
                    onChange={(event) => event.target.value && selectSession(Number(event.target.value))}
                  >
                    <option value="">Choose chat</option>
                    {sessions.map((session) => (
                      <option key={session.id} value={session.id}>{session.title}</option>
                    ))}
                  </select>
                </>
              )}
              {!activeSession && (
                <label className="flex items-center gap-2 text-xs font-medium text-slate-600">
                  <span className="sr-only">Choose a document scope</span>
                  <select
                    className="field max-w-[230px] py-2 text-xs"
                    value={scopeDocumentId}
                    onChange={(event) => setScopeDocumentId(event.target.value)}
                  >
                    <option value="">All accessible documents</option>
                    {documents.map((document) => (
                      <option key={document.id} value={document.id}>{document.title}</option>
                    ))}
                  </select>
                </label>
              )}
            </div>
          </div>
        </header>
        <div className="flex min-h-0 flex-1 flex-col overflow-y-auto px-4 py-6 sm:px-8">
          {activeSession?.messages?.length ? (
            <div className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-5">
              {activeSession.messages.map((message) => (
                <ChatMessage key={message.id} message={message} />
              ))}
              {sending && (
                <div className="flex items-center gap-3 text-sm text-slate-500" role="status" aria-live="polite">
                  <span className="flex h-8 w-8 items-center justify-center rounded-full bg-purple-100 text-purple-700"><Sparkles size={16} /></span>
                  <span className="typing-dots">Searching documents and writing an answer...</span>
                </div>
              )}
              <div ref={messagesEnd} />
            </div>
          ) : (
            <div className="mx-auto flex w-full max-w-2xl flex-1 flex-col items-center justify-center text-center">
              <span className="flex h-16 w-16 items-center justify-center rounded-3xl bg-gradient-to-br from-indigo-100 to-purple-100 text-indigo-700">
                <MessageCircle size={28} />
              </span>
              <h2 className="mt-5 text-xl font-bold text-slate-900">Start with a question</h2>
              <p className="mt-2 max-w-md text-sm leading-6 text-slate-500">
                Answers use only the documents available to you. Pick one document above or search all accessible documents.
              </p>
              <button className="button-secondary mt-5 md:hidden" type="button" onClick={startNewChat}>
                <Plus size={16} /> New chat
              </button>
            </div>
          )}
        </div>
        <form onSubmit={sendMessage} className="border-t border-slate-200 bg-white p-3 sm:p-5">
          <div className="mx-auto flex max-w-3xl items-end gap-2 rounded-2xl border border-slate-200 bg-slate-50 p-2 focus-within:border-indigo-300 focus-within:ring-2 focus-within:ring-indigo-100">
            <label className="sr-only" htmlFor="chat-message">Your question</label>
            <textarea
              id="chat-message"
              className="max-h-40 min-h-11 flex-1 resize-y bg-transparent px-2 py-3 text-sm outline-none placeholder:text-slate-400"
              placeholder="Ask a question about your documents..."
              rows={1}
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={handleKeyDown}
              disabled={sending}
            />
            <button
              className="button-primary h-11 w-11 shrink-0 justify-center !p-0"
              type="submit"
              disabled={sending || !draft.trim()}
              aria-label="Send message"
              title="Send message"
            >
              {sending ? <ArrowUp size={18} className="animate-pulse" /> : <Send size={17} />}
            </button>
          </div>
          <p className="mx-auto mt-2 max-w-3xl text-[11px] text-slate-400">
            Enter to send · Shift+Enter for a new line · your draft remains if a request fails
          </p>
        </form>
      </section>
      <div className="fixed bottom-24 right-4 z-10 md:hidden">
        <button
          className="button-secondary !h-10 !w-10 !rounded-full !p-0 shadow-card"
          type="button"
          onClick={startNewChat}
          aria-label="New chat"
          title="New chat"
        >
          <Plus size={18} />
        </button>
      </div>
    </main>
  );
}
