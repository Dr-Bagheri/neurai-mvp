import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "../api/client";
import type { DocumentInfo } from "../api/types";
import { formatJalali } from "../lib/jalali";
import { useApp } from "../state/AppContext";

const DOC_STATUS_FA: Record<string, { text: string; cls: string }> = {
  uploaded: { text: "در صف نمایه‌سازی", cls: "warn" },
  indexing: { text: "در حال نمایه‌سازی", cls: "warn" },
  indexed: { text: "آمادهٔ پرسش", cls: "ok" },
  failed: { text: "نمایه‌سازی ناموفق", cls: "danger" },
};

export function DocumentsPage() {
  const { d } = useApp();
  const [docs, setDocs] = useState<DocumentInfo[] | null>(null);
  const [error, setError] = useState("");
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const load = () =>
    api
      .listDocuments()
      .then(setDocs)
      .catch((e) => setError(e instanceof Error ? e.message : "خطا در بارگذاری"));

  useEffect(() => {
    void load();
  }, []);

  const upload = async (file: File) => {
    setUploading(true);
    setError("");
    try {
      await api.uploadDocument(file);
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : "بارگذاری ممکن نشد");
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const remove = async (doc: DocumentInfo) => {
    if (!window.confirm(`سند «${doc.filename}» برای همیشه حذف شود؟ (همراه با نمایهٔ جستجو)`)) {
      return;
    }
    await api.deleteDocument(doc.id);
    await load();
  };

  if (error && !docs) return <p className="badge danger">{error}</p>;
  if (!docs) return <p className="muted">در حال بارگذاری…</p>;

  return (
    <>
      <div className="card">
        <div className="row between">
          <h3 style={{ margin: 0 }}>اسناد نمایه‌شدهٔ شما</h3>
          <div className="row">
            <input
              ref={fileRef}
              type="file"
              accept=".pdf,.txt,.md"
              style={{ display: "none" }}
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) void upload(f);
              }}
            />
            <button
              className="btn primary sm"
              disabled={uploading}
              onClick={() => fileRef.current?.click()}
            >
              {uploading ? "در حال بارگذاری…" : "＋ افزودن سند (PDF/TXT/MD)"}
            </button>
          </div>
        </div>
        <p className="muted small">
          اسناد روی سرور دفتر نمایه می‌شوند (بردارسازی محلی) و در «دستیار» و «جستجو» قابل
          پرسش‌اند. هر کاربر فقط اسناد خودش را می‌بیند. حداکثر حجم: {d(50)} مگابایت.
        </p>
        {error && (
          <p className="badge danger" style={{ marginBottom: 8 }}>
            {error}
          </p>
        )}
        {docs.length === 0 ? (
          <div className="empty">هنوز سندی بارگذاری نشده است.</div>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>نام سند</th>
                <th>تاریخ</th>
                <th>وضعیت</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {docs.map((doc) => {
                const st = DOC_STATUS_FA[doc.status] ?? { text: doc.status, cls: "plain" };
                return (
                  <tr key={doc.id}>
                    <td>📄 {doc.filename}</td>
                    <td className="muted">{d(formatJalali(new Date(doc.created_at)))}</td>
                    <td>
                      <span className={`badge ${st.cls}`}>{st.text}</span>
                    </td>
                    <td>
                      <button className="btn danger sm" onClick={() => void remove(doc)}>
                        حذف
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}
