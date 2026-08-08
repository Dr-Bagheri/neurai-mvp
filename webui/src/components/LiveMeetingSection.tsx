// Live meeting controls (D2 v0.3): a RECORDING view — no live captions.
// Setup (title, capture mode, named mics, flags) → recording (state, mic
// list, bookmarks, notepad) → processing (percent progress until the
// transcript arrives). Rendered at the top of the merged Meetings page.
import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, ApiError, wsUrl } from "../api/client";
import type { ActionItem, CaptureMode, MeetingMic, Series } from "../api/types";
import { startMicStream, type MicStream } from "../lib/mic";
import { formatClock } from "../lib/time";
import { useApp } from "../state/AppContext";

type Phase = "setup" | "starting" | "recording" | "processing";

export function LiveMeetingSection({ onMeetingsChanged }: { onMeetingsChanged: () => void }) {
  const { d, cloudReadiness } = useApp();
  const navigate = useNavigate();

  const [phase, setPhase] = useState<Phase>("setup");
  const [expanded, setExpanded] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  // setup form
  const [title, setTitle] = useState("");
  const [mode, setMode] = useState<CaptureMode>("room");
  const [localOnly, setLocalOnly] = useState(true);
  const [confidential, setConfidential] = useState(false);
  const [cloudTranscribe, setCloudTranscribe] = useState(false); // D15 opt-in
  const [seriesList, setSeriesList] = useState<Series[]>([]);
  const [seriesId, setSeriesId] = useState<number | "">("");
  const [resurfaced, setResurfaced] = useState<ActionItem[]>([]);
  // Named mics (D2 v0.3): defined at setup, registered on start; the first
  // one is streamed from THIS device.
  const [micNames, setMicNames] = useState<string[]>(["میکروفون اصلی"]);

  // live state
  const [meetingId, setMeetingId] = useState<number | null>(null);
  const [registeredMics, setRegisteredMics] = useState<MeetingMic[]>([]);
  const [elapsed, setElapsed] = useState(0);
  const [bookmarkCount, setBookmarkCount] = useState(0);
  const [note, setNote] = useState("");
  const [noteSaved, setNoteSaved] = useState(0);

  // processing state
  const [progress, setProgress] = useState<number | null>(null); // null = indeterminate

  const micRef = useRef<MicStream | null>(null);
  const eventsSocketRef = useRef<WebSocket | null>(null);
  const startedAtRef = useRef(0);

  useEffect(() => {
    void api.listSeries().then(setSeriesList).catch(() => setSeriesList([]));
  }, []);

  useEffect(() => {
    if (seriesId === "") {
      setResurfaced([]);
      return;
    }
    void api.resurface(seriesId).then(setResurfaced).catch(() => setResurfaced([]));
  }, [seriesId]);

  useEffect(() => {
    if (phase !== "recording") return;
    const clock = setInterval(
      () => setElapsed(Math.floor((Date.now() - startedAtRef.current) / 1000)),
      1000,
    );
    return () => clearInterval(clock);
  }, [phase]);

  // Post-meeting quality pass: poll status + percent until the transcript
  // arrives («رونوشت در حال آماده‌سازی — ٪N»).
  useEffect(() => {
    if (phase !== "processing" || meetingId === null) return;
    const timer = setInterval(async () => {
      try {
        const m = await api.getMeeting(meetingId);
        if (m.status === "done" || m.status === "failed") {
          clearInterval(timer);
          onMeetingsChanged();
          navigate(`/meetings/${meetingId}`);
          return;
        }
        try {
          const p = await api.meetingProgress(meetingId);
          setProgress(Math.max(0, Math.min(100, p.progress)));
        } catch {
          setProgress(null); // older server: indeterminate bar
        }
      } catch {
        // transient — keep polling
      }
    }, 2500);
    return () => clearInterval(timer);
  }, [phase, meetingId, navigate, onMeetingsChanged]);

  useEffect(
    () => () => {
      eventsSocketRef.current?.close();
      void micRef.current?.stop();
    },
    [],
  );

  // Lifecycle events WS (replaces the removed captions WS): if the meeting is
  // ended from elsewhere (assistant, another device), follow along.
  const enterProcessing = useCallback(() => {
    eventsSocketRef.current?.close();
    eventsSocketRef.current = null;
    void micRef.current?.stop();
    micRef.current = null;
    setProgress(null);
    setPhase("processing");
    onMeetingsChanged();
  }, [onMeetingsChanged]);

  const begin = async () => {
    setError("");
    setPhase("starting");
    let startedId: number | null = null;
    try {
      const meeting = await api.createMeeting({
        title: title.trim(),
        capture_mode: mode,
        language: "fa",
        allow_cloud: !localOnly && !confidential,
        series_id: seriesId === "" ? null : seriesId,
        sensitivity: confidential ? "confidential" : "normal",
        // D15: explicit per-meeting cloud-ASR consent; «محرمانه» always refuses
        cloud_transcribe: cloudTranscribe && !confidential,
      });

      // Register the named mics (v0.3). Older servers 404 here — recording
      // still works with the server-created default mic.
      let mics: MeetingMic[] = [];
      try {
        for (const name of micNames.map((n) => n.trim()).filter(Boolean)) {
          mics.push(await api.addMic(meeting.id, name));
        }
      } catch {
        mics = [];
        setNotice("این نسخهٔ سرور هنوز میکروفون نام‌دار را پشتیبانی نمی‌کند — ضبط با میکروفون پیش‌فرض ادامه می‌یابد.");
      }
      setRegisteredMics(mics);

      await api.startMeeting(meeting.id);
      startedId = meeting.id;
      micRef.current = await startMicStream(meeting.id, mics[0]?.id);

      // lifecycle events (v0.3): {"type":"ended"} → jump to processing
      try {
        const sock = new WebSocket(wsUrl(`/ws/meetings/${meeting.id}/events`));
        sock.onmessage = (e) => {
          try {
            if (JSON.parse(e.data).type === "ended") enterProcessing();
          } catch {
            // non-JSON frame — ignore
          }
        };
        eventsSocketRef.current = sock;
      } catch {
        // events socket is best-effort
      }

      startedAtRef.current = Date.now();
      setMeetingId(meeting.id);
      setPhase("recording");
      onMeetingsChanged();
    } catch (e) {
      await micRef.current?.stop().catch(() => undefined);
      micRef.current = null;
      if (startedId !== null) await api.stopMeeting(startedId).catch(() => undefined);
      setError(
        e instanceof ApiError ? e.detail : e instanceof Error ? e.message : "شروع جلسه ممکن نشد",
      );
      setPhase("setup");
    }
  };

  const addBookmark = useCallback(async () => {
    if (meetingId === null) return;
    await api.addBookmark(meetingId, Date.now() - startedAtRef.current).catch(() => undefined);
    setBookmarkCount((n) => n + 1);
  }, [meetingId]);

  useEffect(() => {
    if (phase !== "recording") return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key.toLowerCase() === "b" && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        void addBookmark();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [phase, addBookmark]);

  const saveNote = async () => {
    if (meetingId === null || !note.trim()) return;
    await api.addNote(meetingId, note.trim(), Date.now() - startedAtRef.current);
    setNote("");
    setNoteSaved((n) => n + 1);
  };

  const finish = async () => {
    if (meetingId === null) return;
    if (!window.confirm("جلسه پایان یابد؟ آماده‌سازی رونوشت بلافاصله شروع می‌شود.")) return;
    try {
      await micRef.current?.stop();
      micRef.current = null;
      await api.stopMeeting(meetingId).catch((e) => {
        if (!(e instanceof ApiError && e.status === 409)) throw e;
      });
      enterProcessing();
    } catch (e) {
      setError(e instanceof Error ? e.message : "توقف جلسه ممکن نشد");
    }
  };

  /** Rename a mic mid-meeting (PATCH; the tag flows to speaker labels). */
  const renameMic = async (mic: MeetingMic) => {
    if (meetingId === null) return;
    const name = window.prompt(`نام جدید برای «${mic.name}»؟`, mic.name);
    if (!name?.trim() || name.trim() === mic.name) return;
    try {
      await api.renameMic(meetingId, mic.id, name.trim());
      setRegisteredMics((list) =>
        list.map((m) => (m.id === mic.id ? { ...m, name: name.trim() } : m)),
      );
    } catch (e) {
      window.alert(e instanceof ApiError ? e.detail : "تغییر نام ممکن نشد");
    }
  };

  // ---- render --------------------------------------------------------------

  if (phase === "processing") {
    return (
      <div className="card">
        <div className="row between">
          <strong>
            رونوشت در حال آماده‌سازی{progress !== null && <> — ٪{d(progress)}</>}
          </strong>
          <span className="badge warn">گذر کیفیت روی GPU</span>
        </div>
        <div
          className={"progress" + (progress === null ? " indeterminate" : "")}
          style={{ marginTop: 10 }}
        >
          <div className="fill" style={progress !== null ? { width: `${progress}%` } : undefined} />
        </div>
        <p className="muted small" style={{ margin: "8px 0 0" }}>
          «{title}» ضبط شد ({d(bookmarkCount)} علامت{noteSaved > 0 && `، ${d(noteSaved)} یادداشت`}).
          پس از آماده شدن رونوشت، به صفحهٔ جلسه می‌روید.
        </p>
      </div>
    );
  }

  if (phase === "recording") {
    return (
      <div className="card">
        <div className="row between wrap">
          <div className="row">
            <span className="live-dot" />
            <strong>{title}</strong>
            <div className="vu">
              <span /><span /><span /><span /><span />
            </div>
            <span className="clock ltr">{d(formatClock(elapsed))}</span>
          </div>
          <div className="row wrap">
            <button className="btn" onClick={() => void addBookmark()} title="Ctrl+B">
              🔖 علامت بزن {bookmarkCount > 0 && `(${d(bookmarkCount)})`}
            </button>
            <button className="btn danger" onClick={() => void finish()}>
              ■ پایان جلسه
            </button>
          </div>
        </div>
        {registeredMics.length > 0 && (
          <div className="row wrap" style={{ marginTop: 10 }}>
            {registeredMics.map((m, i) => (
              <button
                key={m.id}
                className="badge plain"
                style={{ border: "none", cursor: "pointer" }}
                title="نام میکروفون در رونوشت به‌عنوان برچسب گوینده می‌آید — برای تغییر نام کلیک کنید"
                onClick={() => void renameMic(m)}
              >
                🎙️ {m.name}
                {i === 0 && " (این دستگاه)"}
              </button>
            ))}
          </div>
        )}
        {notice && <p className="muted small" style={{ marginTop: 8 }}>{notice}</p>}
        <p className="muted small" style={{ margin: "10px 0 8px" }}>
          ضبط زنده و مقاوم در برابر خرابی است؛ رونوشت باکیفیت بلافاصله پس از پایان جلسه
          آماده می‌شود.
        </p>
        <div className="row">
          <input
            className="input"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="یادداشت جلسه (با مُهر زمانی ذخیره می‌شود)…"
            onKeyDown={(e) => {
              if (e.key === "Enter") void saveNote();
            }}
          />
          <button className="btn sm" disabled={!note.trim()} onClick={() => void saveNote()}>
            ثبت
          </button>
        </div>
        {error && (
          <p className="badge danger" style={{ marginTop: 8 }}>
            {error}
          </p>
        )}
      </div>
    );
  }

  // setup (collapsed teaser or full form)
  if (!expanded) {
    return (
      <div className="card row between">
        <span className="muted">جلسهٔ جدیدی شروع کنید — ضبط زنده، رونوشت پس از پایان.</span>
        <button className="btn primary" onClick={() => setExpanded(true)}>
          ＋ شروع جلسهٔ جدید
        </button>
      </div>
    );
  }

  return (
    <div className="card">
      <div className="row between">
        <h2 style={{ margin: 0 }}>شروع جلسهٔ جدید</h2>
        <button className="btn sm" onClick={() => setExpanded(false)}>
          بستن
        </button>
      </div>
      <label className="small muted">عنوان جلسه</label>
      <input
        className="input"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        placeholder="مثلاً: استندآپ هفتگی تیم محصول"
        style={{ marginBottom: 14 }}
      />

      <label className="small muted">حالت ضبط</label>
      <div className="row wrap" style={{ margin: "6px 0 10px" }}>
        <button
          className={"btn" + (mode === "room" ? " primary" : "")}
          onClick={() => setMode("room")}
        >
          🎙️ میکروفون اتاق
        </button>
        <button
          className={"btn" + (mode === "participants" ? " primary" : "")}
          onClick={() => setMode("participants")}
        >
          👥 میکروفون هر شرکت‌کننده
        </button>
      </div>

      <label className="small muted">
        میکروفون‌های نام‌دار — نام هر میکروفون در رونوشت به‌عنوان برچسب گوینده می‌آید
      </label>
      {micNames.map((name, i) => (
        <div className="row" key={i} style={{ margin: "4px 0" }}>
          <input
            className="input"
            style={{ maxWidth: 320 }}
            value={name}
            onChange={(e) =>
              setMicNames((list) => list.map((n, j) => (j === i ? e.target.value : n)))
            }
            placeholder="مثلاً: میکروفون میز جلسه"
          />
          {i === 0 ? (
            <span className="muted small">(این دستگاه)</span>
          ) : (
            <button
              className="btn danger sm"
              onClick={() => setMicNames((list) => list.filter((_, j) => j !== i))}
            >
              حذف
            </button>
          )}
        </div>
      ))}
      <button
        className="btn sm"
        style={{ margin: "4px 0 14px" }}
        onClick={() => setMicNames((list) => [...list, ""])}
      >
        ＋ افزودن میکروفون
      </button>

      <label className="small muted">سری جلسات (اختیاری)</label>
      <select
        className="input"
        style={{ maxWidth: 320, marginBottom: 8 }}
        value={seriesId}
        onChange={(e) => setSeriesId(e.target.value === "" ? "" : Number(e.target.value))}
      >
        <option value="">— جلسهٔ مستقل —</option>
        {seriesList.map((s) => (
          <option key={s.id} value={s.id}>
            {s.title}
          </option>
        ))}
      </select>
      {resurfaced.length > 0 && (
        <div className="card" style={{ background: "var(--surface-2)", marginBottom: 14 }}>
          <strong className="small">
            📌 کارهای باز از جلسه‌های قبلی این سری ({d(resurfaced.length)})
          </strong>
          <ul className="small muted" style={{ margin: "6px 0 0" }}>
            {resurfaced.map((a) => (
              <li key={a.id}>
                {a.text}
                {a.assignee && ` — ${a.assignee}`}
              </li>
            ))}
          </ul>
        </div>
      )}

      <label className="row" style={{ marginBottom: 8 }}>
        <input
          type="checkbox"
          checked={localOnly}
          disabled={confidential}
          onChange={(e) => setLocalOnly(e.target.checked)}
        />
        🔒 فقط محلی — هیچ بخشی از این جلسه (حتی متن) به مدل ابری فرستاده نشود
      </label>
      <label className="row" style={{ marginBottom: 8 }}>
        <input
          type="checkbox"
          checked={confidential}
          onChange={(e) => {
            setConfidential(e.target.checked);
            if (e.target.checked) {
              setLocalOnly(true);
              setCloudTranscribe(false);
            }
          }}
        />
        🛡️ محرمانه — برای همیشه فقط محلی؛ از جستجوی بین‌جلسه‌ای و پشتیبان‌گیری خارج
      </label>
      {(() => {
        // D15 consent toggle: visible always; disabled with the reason when it
        // cannot take effect. «محرمانه» refuses absolutely (steward ruling).
        const reason = confidential
          ? "جلسه‌های محرمانه هرگز رونویسی ابری نمی‌شوند (حتی با رضایت)"
          : cloudReadiness?.reason === "air_gapped"
            ? "حالت ایزوله فعال است"
            : cloudReadiness?.reason === "offline_mode"
              ? "سرور در حالت آفلاین است — مدیر می‌تواند از «مدیریت سرور» آنلاین کند"
              : null;
        const disabled = reason !== null;
        return (
          <label
            className="row"
            style={{ marginBottom: 14, opacity: disabled ? 0.5 : 1 }}
            title={reason ?? undefined}
          >
            <input
              type="checkbox"
              checked={cloudTranscribe && !disabled}
              disabled={disabled}
              onChange={(e) => setCloudTranscribe(e.target.checked)}
            />
            ☁️ رونویسی ابری — <strong>صدای همین جلسه</strong> با رضایت صریح شما برای
            رونویسی به سرویس ابری فرستاده می‌شود؛ پیش‌فرض همیشه محلی است، خطای ابری به
            رونویسی محلی برمی‌گردد و هر استفاده در گزارش امنیتی ثبت می‌شود
            {disabled && <span className="muted small"> — غیرفعال: {reason}</span>}
          </label>
        );
      })()}

      {error && (
        <p className="badge danger" style={{ marginBottom: 12 }}>
          {error}
        </p>
      )}
      <button
        className="btn primary"
        disabled={!title.trim() || phase === "starting"}
        onClick={() => void begin()}
      >
        {phase === "starting" ? "در حال شروع…" : "● شروع ضبط"}
      </button>
    </div>
  );
}
