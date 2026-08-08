import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, ApiError } from "../api/client";
import type {
  Bookmark,
  Meeting,
  MeetingMic,
  MeetingNote,
  Summary,
  TranscriptSegment,
} from "../api/types";
import { ProvenanceBadge } from "../components/ProvenanceBadge";
import {
  CaptureModeBadge,
  ConfidentialBadge,
  LocalOnlyBadge,
  MeetingStatusBadge,
} from "../components/StatusBadges";
import { formatJalali } from "../lib/jalali";
import { formatClock } from "../lib/time";
import { useApp } from "../state/AppContext";

type Tab = "transcript" | "summaries" | "notes";

const SUMMARY_KIND_FA: Record<string, string> = {
  summary: "خلاصهٔ جلسه",
  action_items: "اقدامات",
  minutes: "صورتجلسه",
  formal: "متن رسمی (نوشتاری)",
};

export function MeetingPage() {
  const { id } = useParams<{ id: string }>();
  const meetingId = Number(id);
  const { d } = useApp();

  const [meeting, setMeeting] = useState<Meeting | null>(null);
  const [segments, setSegments] = useState<TranscriptSegment[]>([]);
  const [bookmarks, setBookmarks] = useState<Bookmark[]>([]);
  const [notes, setNotes] = useState<MeetingNote[]>([]);
  const [summaries, setSummaries] = useState<Summary[]>([]);
  const [error, setError] = useState("");
  const [tab, setTab] = useState<Tab>("transcript");
  const [newNote, setNewNote] = useState("");
  const [playheadMs, setPlayheadMs] = useState(0);
  const [audioAvailable, setAudioAvailable] = useState(true);
  const [progress, setProgress] = useState<number | null>(null);
  const [mics, setMics] = useState<MeetingMic[]>([]);
  const [playbackMic, setPlaybackMic] = useState<number | undefined>(undefined);
  const audioRef = useRef<HTMLAudioElement>(null);

  const load = async () => {
    try {
      const [m, segs, bms, ns, sums] = await Promise.all([
        api.getMeeting(meetingId),
        api.getTranscript(meetingId),
        api.listBookmarks(meetingId),
        api.listNotes(meetingId),
        api.listSummaries(meetingId),
      ]);
      setMeeting(m);
      setSegments(segs);
      setBookmarks(bms);
      setNotes(ns);
      setSummaries(sums);
      // per-mic playback (v0.3) — best-effort
      void api
        .listMics(meetingId)
        .then(setMics)
        .catch(() => setMics([]));
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : "خطا در بارگذاری جلسه");
    }
  };

  useEffect(() => {
    if (Number.isFinite(meetingId)) void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [meetingId]);

  // Quality-pass progress (D2 v0.3): poll percent + status while processing;
  // reload everything when the transcript lands.
  useEffect(() => {
    if (meeting?.status !== "processing") return;
    const timer = setInterval(async () => {
      try {
        const m = await api.getMeeting(meetingId);
        if (m.status !== "processing") {
          clearInterval(timer);
          await load();
          return;
        }
        try {
          const p = await api.meetingProgress(meetingId);
          setProgress(Math.max(0, Math.min(100, p.progress)));
        } catch {
          setProgress(null); // older server — indeterminate
        }
      } catch {
        // transient — keep polling
      }
    }, 2500);
    return () => clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [meeting?.status, meetingId]);

  const activeSegmentId = useMemo(() => {
    const s = segments.find((x) => playheadMs >= x.start_ms && playheadMs < x.end_ms);
    return s?.id ?? null;
  }, [segments, playheadMs]);

  if (error) return <p className="badge danger">{error}</p>;
  if (!meeting) return <p className="muted">در حال بارگذاری…</p>;

  const seekTo = (ms: number) => {
    const audio = audioRef.current;
    if (!audio) return;
    audio.currentTime = ms / 1000;
    void audio.play().catch(() => undefined);
  };

  const relabel = async (speaker: string) => {
    const to = window.prompt(`نام جدید برای «${speaker}»؟`, "");
    if (!to?.trim()) return;
    try {
      await api.relabelSpeaker(meetingId, speaker, to.trim());
      setSegments(await api.getTranscript(meetingId));
    } catch (e) {
      window.alert(e instanceof ApiError ? e.detail : "تغییر نام ممکن نشد");
    }
  };

  const addNote = async () => {
    if (!newNote.trim()) return;
    await api.addNote(meetingId, newNote.trim());
    setNewNote("");
    setNotes(await api.listNotes(meetingId));
  };

  const isLivePass = segments.length > 0 && segments[0].pass_name === "live";

  return (
    <>
      <div className="card">
        <div className="row between wrap">
          <div>
            <h2 style={{ marginBottom: 4 }}>{meeting.title}</h2>
            <div className="muted small">
              {d(formatJalali(new Date(meeting.started_at ?? meeting.created_at), true))}
            </div>
          </div>
          <div className="row wrap">
            <MeetingStatusBadge status={meeting.status} />
            <CaptureModeBadge mode={meeting.capture_mode} />
            <ConfidentialBadge sensitivity={meeting.sensitivity} />
            <LocalOnlyBadge allowCloud={meeting.allow_cloud} />
          </div>
        </div>

        {audioAvailable ? (
          <>
            {mics.length > 1 && (
              <div className="row" style={{ marginTop: 12 }}>
                <span className="muted small">پخش از:</span>
                <select
                  className="input"
                  style={{ maxWidth: 260 }}
                  value={playbackMic ?? ""}
                  onChange={(e) =>
                    setPlaybackMic(e.target.value === "" ? undefined : Number(e.target.value))
                  }
                >
                  <option value="">میکروفون اول</option>
                  {mics.map((m) => (
                    <option key={m.id} value={m.id}>
                      🎙️ {m.name}
                    </option>
                  ))}
                </select>
              </div>
            )}
            <audio
              ref={audioRef}
              controls
              preload="metadata"
              src={api.audioUrl(meetingId, playbackMic)}
              style={{ width: "100%", marginTop: 10 }}
              onTimeUpdate={(e) => setPlayheadMs(e.currentTarget.currentTime * 1000)}
              onError={() => setAudioAvailable(false)}
            />
          </>
        ) : (
          <p className="muted small" style={{ marginTop: 14 }}>
            فایل صوتی این جلسه (هنوز) در دسترس نیست.
          </p>
        )}

        {bookmarks.length > 0 && (
          <div className="row wrap" style={{ marginTop: 10 }}>
            {bookmarks.map((b) => (
              <button key={b.id} className="btn sm" onClick={() => seekTo(b.t_ms)}>
                🔖 {b.note || "علامت"} ({d(formatClock(b.t_ms / 1000))})
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
            className={"tab" + (tab === "summaries" ? " active" : "")}
            onClick={() => setTab("summaries")}
          >
            خلاصه و خروجی‌ها
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
              <div style={{ marginBottom: 16 }}>
                <div className="row between">
                  <strong>
                    رونوشت در حال آماده‌سازی{progress !== null && <> — ٪{d(progress)}</>}
                  </strong>
                  <span className="badge warn">گذر کیفیت روی GPU</span>
                </div>
                <div
                  className={"progress" + (progress === null ? " indeterminate" : "")}
                  style={{ marginTop: 8 }}
                >
                  <div
                    className="fill"
                    style={progress !== null ? { width: `${progress}%` } : undefined}
                  />
                </div>
              </div>
            )}
            {isLivePass && meeting.status === "done" && (
              <p className="badge warn" style={{ marginBottom: 12 }}>
                نمایش رونوشت اولیه (گذر کیفیت هنوز خروجی نداده است).
              </p>
            )}
            {segments.length === 0 ? (
              <div className="empty">هنوز رونوشتی ثبت نشده است.</div>
            ) : (
              <>
                <p className="muted small">
                  روی هر جمله کلیک کنید تا همان لحظه پخش شود؛ روی نام گوینده کلیک کنید تا
                  تغییر نام دهید (به همهٔ بخش‌های همان گوینده اعمال می‌شود).
                </p>
                {segments.map((s) => (
                  <div
                    key={s.id}
                    className={"segment" + (activeSegmentId === s.id ? " playing" : "")}
                    onClick={() => seekTo(s.start_ms)}
                  >
                    <span className="ts">{d(formatClock(s.start_ms / 1000))}</span>
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
                          {s.speaker}:{" "}
                        </span>
                      )}
                      {s.text}
                    </div>
                  </div>
                ))}
              </>
            )}
          </>
        )}

        {tab === "summaries" &&
          (summaries.length === 0 ? (
            <div className="empty">
              هنوز خلاصه‌ای ساخته نشده است. از «دستیار» بخواهید: «این جلسه رو خلاصه کن» —
              خروجی صورتجلسه (Word/PDF/SRT) هم از طریق دستیار و با تأیید شما ساخته می‌شود.
            </div>
          ) : (
            summaries.map((s) => (
              <div key={s.id} style={{ marginBottom: 20 }}>
                <div className="row between">
                  <h3 style={{ margin: 0 }}>{SUMMARY_KIND_FA[s.kind] ?? s.kind}</h3>
                  <div className="row">
                    {s.model && <span className="badge plain ltr">{s.model}</span>}
                    <ProvenanceBadge source={s.source} />
                  </div>
                </div>
                <p style={{ whiteSpace: "pre-wrap" }}>{s.content}</p>
              </div>
            ))
          ))}

        {tab === "notes" && (
          <>
            <div className="row" style={{ marginBottom: 12 }}>
              <input
                className="input"
                value={newNote}
                onChange={(e) => setNewNote(e.target.value)}
                placeholder="یادداشت جدید…"
                onKeyDown={(e) => {
                  if (e.key === "Enter") void addNote();
                }}
              />
              <button className="btn primary sm" disabled={!newNote.trim()} onClick={() => void addNote()}>
                افزودن
              </button>
            </div>
            {notes.length === 0 ? (
              <div className="empty">یادداشتی ثبت نشده است.</div>
            ) : (
              notes.map((n) => (
                <div key={n.id} className="segment" style={{ cursor: "default" }}>
                  <span className="ts">
                    {n.t_ms !== null ? d(formatClock(n.t_ms / 1000)) : "—"}
                  </span>
                  <div>{n.text}</div>
                </div>
              ))
            )}
            <p className="muted small" style={{ marginTop: 10 }}>
              «ادغام یادداشت‌ها با رونوشت» را از دستیار بخواهید تا صورتجلسه‌ای بسازد که
              خودتان در نوشتنش سهیم بوده‌اید.{" "}
              <Link to="/chat">رفتن به دستیار ←</Link>
            </p>
          </>
        )}
      </div>
    </>
  );
}
