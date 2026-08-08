import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { ActionItem, ActionItemStatus } from "../api/types";
import { formatJalali } from "../lib/jalali";
import { useApp } from "../state/AppContext";

const STATUS_LABEL: Record<ActionItemStatus, string> = {
  open: "باز",
  in_progress: "در حال انجام",
  done: "انجام شد",
};

const STATUS_CLASS: Record<ActionItemStatus, string> = {
  open: "warn",
  in_progress: "plain",
  done: "ok",
};

const NEXT_STATUS: Record<ActionItemStatus, ActionItemStatus> = {
  open: "in_progress",
  in_progress: "done",
  done: "open",
};

export function ActionItemsPage() {
  const { d } = useApp();
  const [items, setItems] = useState<ActionItem[] | null>(null);

  useEffect(() => {
    void api.listActionItems().then(setItems);
  }, []);

  if (!items) return <p className="muted">در حال بارگذاری…</p>;

  const open = items.filter((i) => i.status !== "done");
  const done = items.filter((i) => i.status === "done");

  const cycle = async (item: ActionItem) => {
    setItems(await api.setActionItemStatus(item.id, NEXT_STATUS[item.status]));
  };

  const overdue = (i: ActionItem) =>
    i.status !== "done" && i.due_date !== null && new Date(i.due_date) < new Date();

  const renderRow = (i: ActionItem) => (
    <tr key={i.id}>
      <td>
        {i.text}
        <div className="muted small">
          از جلسهٔ <Link to={`/meetings/${i.meeting_id}`}>{i.meeting_title}</Link>
        </div>
      </td>
      <td>{i.assignee}</td>
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
  );

  return (
    <>
      <div className="grid-2" style={{ marginBottom: 16 }}>
        <div className="card stat">
          <span className="muted small">کارهای باز</span>
          <span className="value">{d(open.length)}</span>
        </div>
        <div className="card stat">
          <span className="muted small">انجام‌شده</span>
          <span className="value">{d(done.length)}</span>
        </div>
      </div>

      <div className="card">
        <p className="muted small">
          کارها به‌صورت خودکار از مصوبات جلسه‌ها استخراج می‌شوند و موجودیت زنده‌اند: وقتی
          جلسهٔ بعدیِ یک سری شروع شود، کارهای باز همان سری دوباره روی میز می‌آیند.
        </p>
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
            {open.map(renderRow)}
            {done.map(renderRow)}
          </tbody>
        </table>
      </div>
    </>
  );
}
