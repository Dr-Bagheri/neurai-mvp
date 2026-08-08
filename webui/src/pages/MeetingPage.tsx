import { useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../api/client";
import type { Meeting } from "../api/types";
import { ProvenanceBadge } from "../components/ProvenanceBadge";
import {
  CaptureModeBadge,
  ConfidentialBadge,
  LocalOnlyBadge,
  MeetingStatusBadge,
} from "../components/StatusBadges";
import { formatJalali } from "../lib/jalali";
import { formatClock, formatDurationFa } from "../lib/time";
import { useApp } from "../state/AppContext";

type Tab = "transcript" | "summary" | "minutes" | "notes";

export function MeetingPage() {
  const { id } = useParams<{ id: string }>();
  const { d } = useApp();
  const [meeting, setMeeting] = useState<Meeting | null | undefined>(undefined);
  const [tab, setTab] = useState<Tab>("transcript");

  // Simulated audio-linked playback (D2): a clock stands in for the <audio>
  // element until recordings are served by the engine.
  const [playhead, setPlayhead] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [notesDraft, setNotesDraft] = useState("");
  const notesTimer = useRef<number>();

  useEffect(() => {
    if (!id) return;
    void api.getMeeting(id).then((m) => {
      setMeeting(m);
      if (m) setNotesDraft(m.notes);
    });
  }, [id]);

  useEffect(() => {
    if (!playing) return;
    const t = setInterval(() => setPlayhead((p) => p + 0.5), 500);
    return () => clearInterval(t);
  }, [playing]);

  const activeSegment = useMemo(
    () =>
      meeting?.segments.find((s) => playhead >= s.start_s && playhead < s.end_s)?.id ?? null,
    [meeting, playhead],
  );

  if (meeting === undefined) return <p className="muted">در حال بارگذاری…</p>;
  if (meeting === null) return <p className="muted">جلسه پیدا نشد.</p>;

  const seekTo = (s: number) => {
    setPlayhead(s);
    setPlaying(true);
  };

  const relabel = async (from: string) => {
    const to = window.prompt(`نام جدید برای «${from}»؟`, "");
    if (!to?.trim()) return;
    const updated = await api.relabelSpeaker(meeting.id, from, to.trim());
    if (updated) setMeeting(updated);
  };

  const saveNotes = (value: string) => {
    setNotesDraft(value);
    window.clearTimeout(notesTimer.current);
    notesTimer.current = window.setTimeout(() => {
      void api.saveNotes(meeting.id, value);
    }, 600);
  };

  return (
    <>
      <div className="card">
        <div className="row between wrap">
          <div>
            <h2 style={{ marginBottom: 4 }}>{meeting.title}</h2>
            <div className="muted small">
              {d(formatJalali(new Date(meeting.started_at), true))} ·{" "}
              {d(formatDurationFa(meeting.duration_s))} · {meeting.participants.join("، ")}
            </div>
          </div>
          <div className="row wrap">
            <MeetingStatusBadge status={meeting.status} />
            <CaptureModeBadge mode={meeting.capture_mode} />
            <ConfidentialBadge sensitivity={meeting.sensitivity} />
            <LocalOnlyBadge localOnly={meeting.local_only} />
          </div>
        </div>

        <div className="player" style={{ marginTop: 14 }}>
          <button className="btn sm" onClick={() => setPlaying((p) => !p)}>
            {playing ? "⏸" : "▶"}
          </button>
          <div
            className="bar"
            onClick={(e) => {
              const r = e.currentTarget.getBoundingClientRect();
              const frac = (e.clientX - r.left) / r.width;
              setPlayhead(frac * meeting.duration_s);
            }}
          >
            <div
              className="fill"
              style={{ width: `${(playhead / meeting.duration_s) * 100}%` }}
            />
          </div>
          <span className="clock">
            {d(formatClock(playhead))} / {d(formatClock(meeting.duration_s))}
          </span>
        </div>
        {meeting.bookmarks.length > 0 && (
          <div className="row wrap" style={{ marginTop: 10 }}>
            {meeting.bookmarks.map((b) => (
              <button key={b.id} className="btn sm" onClick={() => seekTo(b.at_s)}>
                🔖 {b.label} ({d(formatClock(b.at_s))})
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="card">
        <div className="tabs">
          <button
            className={"tab" + (tab === "transcript" ? " active" : "")}
            onClick={() => setTab("transcript")}
          >
            رونوشت
          </button>
          <button
            className={"tab" + (tab === "summary" ? " active" : "")}
            onClick={() => setTab("summary")}
          >
            خلاصه و مصوبات
          </button>
          <button
            className={"tab" + (tab === "minutes" ? " active" : "")}
            onClick={() => setTab("minutes")}
          >
            صورتجلسه و خروجی
          </button>
          <button
            className={"tab" + (tab === "notes" ? " active" : "")}
            onClick={() => setTab("notes")}
          >
            یادداشت‌ها
          </button>
        </div>

        {tab === "transcript" && (
          <>
            {meeting.status === "processing" && (
              <p className="badge warn" style={{ marginBottom: 12 }}>
                گذر کیفیت در حال اجراست — این رونوشتِ زندهٔ تقریبی است و به‌زودی با نسخهٔ
                دقیقِ دارای برچسب گوینده جایگزین می‌شود.
              </p>
            )}
            <p className="muted small">
              روی هر جمله کلیک کنید تا همان لحظه پخش شود؛ روی نام گوینده کلیک کنید تا
              تغییر نام دهید (به همهٔ بخش‌های همان گوینده اعمال می‌شود).
            </p>
            {meeting.segments.map((s) => (
              <div
                key={s.id}
                className={"segment" + (activeSegment === s.id ? " playing" : "")}
                onClick={() => seekTo(s.start_s)}
              >
                <span className="ts">{d(formatClock(s.start_s))}</span>
                <div>
                  {s.speaker && (
                    <span
                      className="speaker"
                      title="تغییر نام گوینده"
                      onClick={(e) => {
                        e.stopPropagation();
                        void relabel(s.speaker!);
                      }}
                    >
                      {s.speaker}:
                    </span>
                  )}
                  {s.bookmarked && <span className="bookmark-flag">🔖 </span>}
                  {s.text}
                </div>
              </div>
            ))}
          </>
        )}

        {tab === "summary" &&
          (meeting.summary ? (
            <>
              <div className="row between">
                <h3>خلاصهٔ جلسه</h3>
                <ProvenanceBadge provenance={meeting.summary.provenance} />
              </div>
              <p>{meeting.summary.overview}</p>
              <h3 style={{ marginTop: 18 }}>مصوبات</h3>
              <ol>
                {meeting.summary.decisions.map((dec, i) => (
                  <li key={i}>{dec}</li>
                ))}
              </ol>
            </>
          ) : (
            <div className="empty">
              خلاصه پس از پایان گذر کیفیت ساخته می‌شود.
            </div>
          ))}

        {tab === "minutes" && (
          <>
            <h3>خروجی صورتجلسه</h3>
            <p className="muted small">
              متن گفتاری رونوشت پیش از خروجی، به فارسی رسمی (نوشتاری) تبدیل می‌شود؛ تاریخ‌ها
              شمسی و قالب شامل حاضرین، دستور جلسه، مصوبات با مسئول هر بند و محل امضاست.
            </p>
            <div className="row wrap" style={{ marginBottom: 16 }}>
              <select className="input" style={{ width: 260 }} defaultValue="official">
                <option value="official">صورتجلسهٔ رسمی (اداری)</option>
                <option value="standup">قالب استندآپ</option>
                <option value="decision">قالب جلسهٔ تصمیم‌گیری</option>
              </select>
              <button
                className="btn"
                onClick={() => window.alert("در نسخهٔ نمایشی، خروجی Word توسط سرور ساخته می‌شود.")}
              >
                خروجی Word
              </button>
              <button
                className="btn"
                onClick={() => window.alert("در نسخهٔ نمایشی، خروجی PDF توسط سرور ساخته می‌شود.")}
              >
                خروجی PDF
              </button>
              <button
                className="btn"
                onClick={() => window.alert("در نسخهٔ نمایشی، زیرنویس SRT توسط سرور ساخته می‌شود.")}
              >
                زیرنویس SRT
              </button>
            </div>
            <div className="card" style={{ background: "var(--surface-2)" }}>
              <h3 style={{ textAlign: "center" }}>صورتجلسه</h3>
              <p>
                <strong>موضوع:</strong> {meeting.title}
                <br />
                <strong>تاریخ:</strong> {d(formatJalali(new Date(meeting.started_at), true))}
                <br />
                <strong>حاضرین:</strong> {meeting.participants.join("، ")}
              </p>
              <p>
                <strong>مصوبات:</strong>
              </p>
              <ol>
                {(meeting.summary?.decisions ?? ["— پس از پایان پردازش تکمیل می‌شود —"]).map(
                  (dec, i) => (
                    <li key={i}>{dec}</li>
                  ),
                )}
              </ol>
              <div className="row between" style={{ marginTop: 24 }}>
                {meeting.participants.map((p) => (
                  <div key={p} className="small muted" style={{ textAlign: "center" }}>
                    {p}
                    <br />
                    امضا: ..................
                  </div>
                ))}
              </div>
            </div>
          </>
        )}

        {tab === "notes" && (
          <>
            <div className="row between">
              <h3>یادداشت‌های شما</h3>
              <button
                className="btn sm"
                onClick={() =>
                  window.alert(
                    "مهارت «ادغام یادداشت‌ها»: دستیار یادداشت‌های شما را با رونوشت ترکیب می‌کند و صورتجلسهٔ ساخت‌یافته می‌سازد. (در نسخهٔ نمایشی غیرفعال)",
                  )
                }
              >
                🤝 ادغام با رونوشت
              </button>
            </div>
            <textarea
              className="input"
              style={{ minHeight: 200 }}
              value={notesDraft}
              onChange={(e) => saveNotes(e.target.value)}
              placeholder="در طول جلسه یادداشتی ثبت نشده است."
            />
            <p className="muted small">ذخیرهٔ خودکار فعال است.</p>
          </>
        )}
      </div>
    </>
  );
}
