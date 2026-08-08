import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { ActionItem } from "../api/types";
import { formatJalali } from "../lib/jalali";
import { useApp } from "../state/AppContext";

type Status = ActionItem["status"];

const STATUS_LABEL: Record<Status, string> = {
  open: "باز",
  done: "انجام شد",
  dropped: "منتفی",
};

const STATUS_CLASS: Record<Status, string> = {
  open: "warn",
  done: "ok",
  dropped: "plain",
};

const NEXT_STATUS: Record<Status, Status> = {
  open: "done",
  done: "dropped",
  dropped: "open",
};

export function ActionItemsPage() {
  const { d } = useApp();
  const [items, setItems] = useState<ActionItem[] | null>(null);
  const [error, setError] = useState("");

  const load = () =>
    api
      .listActionItems()
      .then(setItems)
      .catch((e) => setError(e instanceof Error ? e.message : "خطا در بارگذاری"));

  useEffect(() => {
    void load();
  }, []);

  if (error) return <p className="badge danger">{error}</p>;
  if (!items) return <p className="muted">در حال بارگذاری…</p>;

  const open = items.filter((i) => i.status === "open");

  const cycle = async (item: ActionItem) => {
    await api.updateActionItem(item.id, { status: NEXT_STATUS[item.status] });
    await load();
  };

  const overdue = (i: ActionItem) =>
    i.status === "open" && i.due_date !== null && new Date(i.due_date) < new Date();

  return (
    <>
      <div className="grid-2" style={{ marginBottom: 16 }}>
        <div className="card stat">
          <span className="muted small">کارهای باز</span>
          <span className="value">{d(open.length)}</span>
        </div>
        <div className="card stat">
          <span className="muted small">کل کارها</span>
          <span className="value">{d(items.length)}</span>
        </div>
      </div>

      <div className="card">
        <p className="muted small">
          کارها از مصوبات جلسه‌ها استخراج می‌شوند و موجودیت زنده‌اند: با شروع جلسهٔ بعدیِ
          یک سری، کارهای باز همان سری دوباره روی میز می‌آیند. برای تغییر وضعیت روی نشان
          وضعیت کلیک کنید.
        </p>
        {items.length === 0 ? (
          <div className="empty">
            هنوز کاری ثبت نشده — بعد از خلاصه‌سازی اولین جلسه، اقدامات اینجا ظاهر می‌شوند.
          </div>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>کار</th>
                <th>مسئول</th>
                <th>موعد</th>
                <th>وضعیت</th>
              </tr>
            </thead>
            <tbody>
              {items.map((i) => (
                <tr key={i.id}>
                  <td>
                    {i.text}
                    {i.meeting_id !== null && (
                      <div className="muted small">
                        از <Link to={`/meetings/${i.meeting_id}`}>جلسهٔ {d(i.meeting_id)}</Link>
                      </div>
                    )}
                  </td>
                  <td>{i.assignee || "—"}</td>
                  <td className="muted">
                    {i.due_date ? (
                      <>
                        {d(formatJalali(new Date(i.due_date)))}{" "}
                        {overdue(i) && <span className="badge danger">گذشته!</span>}
                      </>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td>
                    <button
                      className={`badge ${STATUS_CLASS[i.status]}`}
                      style={{ border: "none", cursor: "pointer" }}
                      title="برای تغییر وضعیت کلیک کنید"
                      onClick={() => void cycle(i)}
                    >
                      {STATUS_LABEL[i.status]}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}
