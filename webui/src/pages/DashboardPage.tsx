import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { Meeting, Series } from "../api/types";
import { LiveMeetingSection } from "../components/LiveMeetingSection";
import {
  CaptureModeBadge,
  ConfidentialBadge,
  LocalOnlyBadge,
  MeetingStatusBadge,
} from "../components/StatusBadges";
import { formatDurationFa } from "../lib/time";
import { formatJalali } from "../lib/jalali";
import { useApp } from "../state/AppContext";
import { useChat } from "../state/ChatContext";

function durationSeconds(m: Meeting): number | null {
  if (!m.started_at || !m.ended_at) return null;
  const ms = new Date(m.ended_at).getTime() - new Date(m.started_at).getTime();
  return ms > 0 ? ms / 1000 : null;
}

export function DashboardPage() {
  const { d } = useApp();
  const { mutationCounter } = useChat();
  const [meetings, setMeetings] = useState<Meeting[] | null>(null);
  const [series, setSeries] = useState<Series[]>([]);
  const [error, setError] = useState("");
  const [reloadNonce, setReloadNonce] = useState(0);

  // mutationCounter: refetch after a confirmed assistant action (e.g. the
  // assistant deleted a meeting); reloadNonce: after live-section events.
  useEffect(() => {
    void Promise.all([api.listMeetings(), api.listSeries()])
      .then(([ms, ss]) => {
        setMeetings(ms);
        setSeries(ss);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "خطا در بارگذاری"));
  }, [mutationCounter, reloadNonce]);

  if (error) return <p className="badge danger">{error}</p>;
  if (!meetings) return <p className="muted">در حال بارگذاری…</p>;

  const seriesTitle = new Map(series.map((s) => [s.id, s.title]));

  return (
    <>
      <LiveMeetingSection onMeetingsChanged={() => setReloadNonce((n) => n + 1)} />

      <p className="muted" style={{ margin: "16px 0 8px" }}>
        {d(meetings.length)} جلسه در بایگانی شما
      </p>

      <div className="card" style={{ padding: 0 }}>
        {meetings.length === 0 ? (
          <div className="empty">
            هنوز جلسه‌ای ثبت نشده است — از «شروع جلسهٔ جدید» شروع کنید.
          </div>
        ) : (
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
              {meetings.map((m) => {
                const dur = durationSeconds(m);
                return (
                  <tr key={m.id}>
                    <td>
                      <Link to={`/meetings/${m.id}`}>
                        <strong>{m.title}</strong>
                      </Link>
                      <span style={{ marginInlineStart: 8 }}>
                        <ConfidentialBadge sensitivity={m.sensitivity} />{" "}
                        <LocalOnlyBadge allowCloud={m.allow_cloud} />
                      </span>
                      {m.series_id !== null && (
                        <div className="muted small">
                          🔁 {seriesTitle.get(m.series_id) ?? `سری ${d(m.series_id)}`}
                        </div>
                      )}
                    </td>
                    <td className="muted">
                      {d(formatJalali(new Date(m.started_at ?? m.created_at)))}
                    </td>
                    <td className="muted">{dur !== null ? d(formatDurationFa(dur)) : "—"}</td>
                    <td>
                      <CaptureModeBadge mode={m.capture_mode} />
                    </td>
                    <td>
                      <MeetingStatusBadge status={m.status} />
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
