import { LoaderCircle } from "lucide-react";

export default function Loader({ label = "Loading...", fullPage = false }) {
  return (
    <div
      className={`flex items-center justify-center gap-2 text-slate-500 ${
        fullPage ? "min-h-[60vh]" : "py-8"
      }`}
      role="status"
      aria-live="polite"
    >
      <LoaderCircle className="animate-spin" size={20} aria-hidden="true" />
      <span>{label}</span>
    </div>
  );
}
