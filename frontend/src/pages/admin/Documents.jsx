import { FileUp, LoaderCircle, RefreshCw, Trash2, UploadCloud } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import toast from "react-hot-toast";
import { api } from "../../api/client";
import Loader from "../../components/Loader";

function statusClass(value) {
  if (value === "ready") return "bg-emerald-50 text-emerald-700";
  if (value === "failed") return "bg-rose-50 text-rose-700";
  if (value === "processing") return "bg-amber-50 text-amber-700";
  return "bg-slate-100 text-slate-600";
}

export default function AdminDocuments() {
  const [documents, setDocuments] = useState([]);
  const [file, setFile] = useState(null);
  const [title, setTitle] = useState("");
  const [isPublic, setIsPublic] = useState(true);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const fileInput = useRef(null);

  const load = useCallback(async () => {
    const { data } = await api.get("/documents", { params: { limit: 500 } });
    setDocuments(data);
  }, []);

  useEffect(() => {
    load()
      .catch((error) => toast.error(error.userMessage || "Could not load documents."))
      .finally(() => setLoading(false));
  }, [load]);

  async function upload(event) {
    event.preventDefault();
    if (!file || uploading) return;
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      toast.error("Choose a PDF file.");
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      toast.error("The maximum PDF size is 10 MB.");
      return;
    }
    const body = new FormData();
    body.append("file", file);
    if (title.trim()) body.append("title", title.trim());
    body.append("is_public", String(isPublic));
    setUploading(true);
    setUploadProgress(0);
    try {
      const { data } = await api.post("/documents/upload", body, {
        headers: { "Content-Type": "multipart/form-data" },
        onUploadProgress: (progress) => {
          if (progress.total) setUploadProgress(Math.round((progress.loaded / progress.total) * 100));
        },
      });
      toast.success(data.status === "ready" ? "PDF indexed and ready." : "PDF upload accepted.");
      setFile(null);
      setTitle("");
      if (fileInput.current) fileInput.current.value = "";
      await load();
    } catch (error) {
      toast.error(error.userMessage || "Upload or indexing failed. You can try again.");
      try {
        await load();
      } catch (refreshError) {
        toast.error(refreshError.userMessage || "The document list could not be refreshed.");
      }
    } finally {
      setUploading(false);
    }
  }

  async function setVisibility(document) {
    try {
      await api.patch(`/documents/${document.id}/visibility`, {
        is_public: !document.is_public,
      });
      toast.success("Document visibility updated.");
      await load();
    } catch (error) {
      toast.error(error.userMessage || "Could not update visibility.");
    }
  }

  async function remove(document) {
    if (!window.confirm(`Delete "${document.title}", its PDF, and its vector index? Existing chat history will remain.`)) return;
    try {
      await api.delete(`/documents/${document.id}`);
      toast.success("Document deleted.");
      await load();
    } catch (error) {
      toast.error(error.userMessage || "Could not delete this document.");
    }
  }

  return (
    <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
      <p className="text-sm font-semibold text-indigo-600">Administration</p>
      <h1 className="mt-1 text-3xl font-bold text-slate-900">Documents</h1>
      <p className="mt-2 text-sm text-slate-500">Upload text-based PDFs. Scanned PDFs need OCR, which is not enabled.</p>

      <form className="card mt-7" onSubmit={upload}>
        <div className="flex items-center gap-2">
          <FileUp className="text-indigo-600" size={20} />
          <h2 className="font-semibold text-slate-900">Add a document</h2>
        </div>
        <div className="mt-5 grid gap-4 md:grid-cols-[1fr_1fr_auto] md:items-end">
          <label className="block text-sm font-medium text-slate-700">
            PDF file (max 10 MB)
            <input
              ref={fileInput}
              className="field mt-2"
              type="file"
              accept="application/pdf,.pdf"
              required
              disabled={uploading}
              onChange={(event) => setFile(event.target.files?.[0] || null)}
            />
          </label>
          <label className="block text-sm font-medium text-slate-700">
            Display title (optional)
            <input className="field mt-2" maxLength={255} value={title} onChange={(event) => setTitle(event.target.value)} disabled={uploading} placeholder="Use the filename by default" />
          </label>
          <div className="flex items-center gap-3">
            <label className="flex min-h-10 items-center gap-2 text-sm text-slate-700">
              <input className="h-4 w-4 accent-indigo-600" type="checkbox" checked={isPublic} onChange={(event) => setIsPublic(event.target.checked)} disabled={uploading} />
              Public
            </label>
            <button className="button-primary" type="submit" disabled={!file || uploading}>
              {uploading ? <LoaderCircle size={17} className="animate-spin" /> : <UploadCloud size={17} />}
              {uploading ? `${uploadProgress}%` : "Upload"}
            </button>
          </div>
        </div>
        {uploading && (
          <div className="mt-4" role="status" aria-live="polite">
            <div className="h-2 overflow-hidden rounded-full bg-slate-100">
              <div className="h-full rounded-full bg-gradient-to-r from-indigo-600 to-purple-600 transition-all" style={{ width: `${uploadProgress}%` }} />
            </div>
            <p className="mt-2 text-xs text-slate-500">Uploading and indexing… please keep this page open.</p>
          </div>
        )}
      </form>

      <section className="card mt-5">
        <div className="flex items-center justify-between">
          <h2 className="font-semibold text-slate-900">Library</h2>
          <button className="icon-button" type="button" onClick={() => load().catch((error) => toast.error(error.userMessage || "Could not refresh documents."))} aria-label="Refresh documents">
            <RefreshCw size={17} />
          </button>
        </div>
        {loading ? <Loader label="Loading documents..." /> : documents.length === 0 ? (
          <div className="py-12 text-center text-sm text-slate-500">No PDFs yet. Upload one to make it available for chat.</div>
        ) : (
          <div className="mt-4 overflow-x-auto">
            <table className="w-full min-w-[920px] text-left text-sm">
              <thead className="border-b border-slate-100 text-xs uppercase tracking-wide text-slate-400">
                <tr><th className="px-3 py-3">Document</th><th className="px-3 py-3">Processing</th><th className="px-3 py-3">Visibility</th><th className="px-3 py-3">Index</th><th className="px-3 py-3">Uploaded</th><th className="px-3 py-3 text-right">Actions</th></tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {documents.map((document) => (
                  <tr key={document.id}>
                    <td className="max-w-[280px] px-3 py-4">
                      <p className="truncate font-medium text-slate-800">{document.title}</p>
                      <p className="mt-1 truncate text-xs text-slate-500">{document.filename}</p>
                    </td>
                    <td className="px-3 py-4">
                      <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${statusClass(document.status)}`}>{document.status}</span>
                      {document.processing_error && <p className="mt-2 max-w-[220px] text-xs text-rose-600">{document.processing_error}</p>}
                    </td>
                    <td className="px-3 py-4">
                      <button type="button" className="min-h-9 rounded-lg px-2 text-xs font-medium text-indigo-700 hover:bg-indigo-50" onClick={() => setVisibility(document)} aria-label={`${document.is_public ? "Make private" : "Make public"}: ${document.title}`}>
                        {document.is_public ? "Public · change" : "Private · change"}
                      </button>
                    </td>
                    <td className="px-3 py-4 text-xs text-slate-600">{document.chunk_count} chunks · {document.page_count ?? "—"} pages</td>
                    <td className="px-3 py-4 text-xs text-slate-500">{new Date(document.created_at).toLocaleDateString()}</td>
                    <td className="px-3 py-4 text-right">
                      <button type="button" className="icon-button ml-auto hover:!text-rose-600" onClick={() => remove(document)} aria-label={`Delete ${document.title}`}>
                        <Trash2 size={17} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </main>
  );
}
