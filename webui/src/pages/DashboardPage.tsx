import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { Meeting } from "../api/types";
import {
  CaptureModeBadge,
  ConfidentialBadge,
  LocalOnlyBadge,
  MeetingStatusBadge,
} from "../components/StatusBadges";
import { formatDurationFa } from "../lib/time";
import { formatJalali } from "../lib/jalali";
import { useApp } from "../state/AppContext";

export function DashboardPage() {
  const { d } = useApp();
  const navigate = useNavigate();
  const [meetings, setMeetings] = useState<Meeting[] | null>(null);

  useEffect(() => {
    void api.listMeetings().then(setMeetings);
  }, []);

  if (!meetings) return <p className="muted">در حال بارگذاری…</p>;

  const series = new Map<string, Meeting[]>();
  for (const m of meetings) {
    if (m.series_name) {
      series.set(m.series_name, [...(series.get(m.series_name) ?? []), m]);
    }
  }

  return (
    <>
      <div className="row between" style={{ marginBottom: 16 }}>
        <p className="muted" style={{ margin: 0 }}>
          {d(meetings.length)} جلسه در بایگانی شما
        </p>
        <button className="btn primary" onClick={() => navigate("/live")}>
          ＋ شروع جلسهٔ جدید
        </button>
      </div>

      {[...series.entries()].map(([name, list]) =>
        list.length > 1 ? (
          <div className="card" key={name} style={{ marginBottom: 16 }}>
            <div className="row between">
              <h3 style={{ margin: 0 }}>🔁 سری جلسات: {name}</h3>
              <span className="muted small">{d(list.length)} جلسه</span>
            </div>
            <p className="muted small" style={{ margin: "6px 0 0" }}>
              با شروع جلسهٔ بعدی این سری، کارهای باز و «از جلسهٔ قبل چه گذشت» به‌صورت خودکار
              نمایش داده می‌شود.
            </p>
          </div>
        ) : null,
      )}

      <div className="card" style={{ padding: 0 }}>
        <table className="table">
          <thead>
            <tr>
              <th>عنوان</th>
              <th>تاریخ</th>
              <th>مدت</th>
              <th>حالت ضبط</th>
              <th>وضعیت</th>
            </tr>
          </thead>
          <tbody>
            {meetings.map((m) => (
              <tr key={m.id}>
                <td>
                  <Link to={`/meetings/${m.id}`}>
                    <strong>{m.title}</strong>
                  </Link>
                  <span style={{ marginInlineStart: 8 }} className="row" >
                    <ConfidentialBadge sensitivity={m.sensitivity} />
                    <LocalOnlyBadge localOnly={m.local_only} />
                  </span>
                  <div className="muted small">{m.participants.join("، ")}</div>
                </td>
                <td className="muted">{d(formatJalali(new Date(m.started_at)))}</td>
                <td className="muted">{d(formatDurationFa(m.duration_s))}</td>
                <td>
                  <CaptureModeBadge mode={m.capture_mode} />
                </td>
                <td>
                  <MeetingStatusBadge status={m.status} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
