import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { DocumentInfo } from "../api/types";
import { formatJalali } from "../lib/jalali";
import { useApp } from "../state/AppContext";

export function DocumentsPage() {
  const { d } = useApp();
  const [docs, setDocs] = useState<DocumentInfo[] | null>(null);

  useEffect(() => {
    void api.listDocuments().then(setDocs);
  }, []);

  if (!docs) return <p className="muted">در حال بارگذاری…</p>;

  return (
    <>
      <div className="card">
        <div className="row between">
          <h3 style={{ margin: 0 }}>اسناد نمایه‌شدهٔ شما</h3>
          <button
            className="btn primary sm"
            onClick={() =>
              window.alert("در نسخهٔ نمایشی بارگذاری غیرفعال است؛ در محصول، فایل PDF/Word روی سرور دفتر نمایه می‌شود.")
            }
          >
            ＋ افزودن سند
          </button>
        </div>
        <p className="muted small">
          اسناد روی سرور دفتر نمایه می‌شوند (بردارسازی محلی با BGE-M3) و در چت و جستجو قابل
          پرسش‌اند. هر کاربر فقط اسناد خودش یا اسنادی که با او به اشتراک گذاشته شده را می‌بیند.
        </p>
        <table className="table">
          <thead>
            <tr>
              <th>نام سند</th>
              <th>صفحات</th>
              <th>تاریخ نمایه‌سازی</th>
            </tr>
          </thead>
          <tbody>
            {docs.map((doc) => (
              <tr key={doc.id}>
                <td>📄 {doc.name}</td>
                <td className="muted">{d(doc.pages)}</td>
                <td className="muted">{d(formatJalali(new Date(doc.indexed_at)))}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card">
        <h3>پرسش از اسناد</h3>
        <p className="muted small">
          سؤال‌های خود را در بخش «دستیار» بپرسید — دستیار با مهارت{" "}
          <span className="ltr">search_documents</span> پاسخ را از همین اسناد پیدا می‌کند و
          منبع را نشان می‌دهد. بازیابی همیشه محلی است؛ فقط تولید پاسخ ممکن است (با رضایت) به
          مدل ابری برود.
        </p>
      </div>
    </>
  );
}
