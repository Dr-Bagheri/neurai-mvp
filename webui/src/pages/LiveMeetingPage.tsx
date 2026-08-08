import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { LIVE_CAPTION_FEED } from "../api/mock";
import type { CaptureMode } from "../api/types";
import { formatClock } from "../lib/time";
import { useApp } from "../state/AppContext";

interface LiveBookmark {
  at_s: number;
  label: string;
}

type Phase = "setup" | "recording" | "ended";

export function LiveMeetingPage() {
  const { d } = useApp();
  const navigate = useNavigate();

  const [phase, setPhase] = useState<Phase>("setup");
  const [title, setTitle] = useState("");
  const [mode, setMode] = useState<CaptureMode>("room_mic");
  const [localOnly, setLocalOnly] = useState(true);
  const [confidential, setConfidential] = useState(false);
  const [enrollment, setEnrollment] = useState(true);

  const [elapsed, setElapsed] = useState(0);
  const [captions, setCaptions] = useState<string[]>([]);
  const [bookmarks, setBookmarks] = useState<LiveBookmark[]>([]);
  const [notes, setNotes] = useState("");
  const captionsRef = useRef<HTMLDivElement>(null);

  // Simulated live pass: a caption every few seconds + a running clock.
  // Real implementation: WebSocket → VAD → faster-whisper live model (D2).
  useEffect(() => {
    if (phase !== "recording") return;
    const clock = setInterval(() => setElapsed((s) => s + 1), 1000);
    let i = 0;
    const feed = setInterval(() => {
      setCaptions((c) => [...c, LIVE_CAPTION_FEED[i % LIVE_CAPTION_FEED.length]]);
      i += 1;
    }, 4000);
    return () => {
      clearInterval(clock);
      clearInterval(feed);
    };
  }, [phase]);

  useEffect(() => {
    captionsRef.current?.scrollTo({ top: captionsRef.current.scrollHeight, behavior: "smooth" });
  }, [captions]);

  const addBookmark = () => {
    setBookmarks((b) => [...b, { at_s: elapsed, label: `لحظهٔ ${formatClock(elapsed)}` }]);
  };

  useEffect(() => {
    if (phase !== "recording") return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key.toLowerCase() === "b" && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        addBookmark();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phase, elapsed]);

  if (phase === "setup") {
    return (
      <div className="card" style={{ maxWidth: 640 }}>
        <h2>شروع جلسهٔ جدید</h2>
        <label className="small muted">عنوان جلسه</label>
        <input
          className="input"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="مثلاً: استندآپ هفتگی تیم محصول"
          style={{ marginBottom: 14 }}
        />

        <label className="small muted">حالت ضبط (قابل انتخاب برای هر جلسه)</label>
        <div className="row wrap" style={{ margin: "6px 0 14px" }}>
          <button
            className={"btn" + (mode === "room_mic" ? " primary" : "")}
            onClick={() => setMode("room_mic")}
          >
            🎙️ میکروفون اتاق — یک دستگاه برای همه
          </button>
          <button
            className={"btn" + (mode === "per_participant" ? " primary" : "")}
            onClick={() => setMode("per_participant")}
          >
            👥 میکروفون هر شرکت‌کننده — برچسب گوینده دقیق
          </button>
        </div>
        {mode === "room_mic" ? (
          <p className="muted small">
            گویندگان پس از پایان جلسه با تفکیک گوینده مشخص می‌شوند؛ می‌توانید جلسه را با «دور
            معارفه» شروع کنید تا نام‌ها به‌صورت خودکار شناسایی شوند.
          </p>
        ) : (
          <p className="muted small">
            هر شرکت‌کننده از مرورگر خودش به این جلسه می‌پیوندد؛ برچسب گوینده‌ها از روی حساب
            کاربری، دقیق و بدون نیاز به تفکیک گوینده ثبت می‌شود.
          </p>
        )}

        {mode === "room_mic" && (
          <label className="row" style={{ marginBottom: 10 }}>
            <input
              type="checkbox"
              checked={enrollment}
              onChange={(e) => setEnrollment(e.target.checked)}
            />
            شروع با دور معارفه («سلام، من … هستم») برای شناسایی خودکار گوینده‌ها
          </label>
        )}

        <label className="row" style={{ marginBottom: 10 }}>
          <input
            type="checkbox"
            checked={localOnly}
            disabled={confidential}
            onChange={(e) => setLocalOnly(e.target.checked)}
          />
          🔒 فقط محلی — هیچ بخشی از این جلسه (حتی متن) به مدل ابری فرستاده نشود
        </label>
        <label className="row" style={{ marginBottom: 18 }}>
          <input
            type="checkbox"
            checked={confidential}
            onChange={(e) => {
              setConfidential(e.target.checked);
              if (e.target.checked) setLocalOnly(true);
            }}
          />
          🛡️ محرمانه — برای همیشه فقط محلی؛ از جستجوی بین‌جلسه‌ای و پشتیبان‌گیری خارج و
          فقط برای افراد مشخص‌شده قابل مشاهده
        </label>
        <p className="muted small" style={{ marginTop: -10 }}>
          صدا در هیچ حالتی از سرور خارج نمی‌شود؛ گزینهٔ «فقط محلی» پردازش متنی را هم کاملاً
          محلی نگه می‌دارد.
        </p>

        <button
          className="btn primary"
          disabled={!title.trim()}
          onClick={() => setPhase("recording")}
        >
          ● شروع ضبط
        </button>
      </div>
    );
  }

  if (phase === "ended") {
    return (
      <div className="card" style={{ maxWidth: 640 }}>
        <h2>جلسه پایان یافت ✅</h2>
        <p>
          ضبط جلسهٔ «{title}» ذخیره شد. <strong>گذر کیفیت</strong> (رونویسی دقیق با مدل بزرگ
          فارسی{mode === "room_mic" ? " + تفکیک و شناسایی گوینده" : ""}) در صف پردازش قرار
          گرفت — رونوشت نهایی چند دقیقهٔ دیگر آماده می‌شود.
        </p>
        <ul className="muted small">
          <li>{d(captions.length)} خط کپشن زنده ثبت شد</li>
          <li>{d(bookmarks.length)} علامت‌گذاری در طول جلسه</li>
          {notes.trim() && <li>یادداشت‌های شما ذخیره شد و بعداً با رونوشت ادغام می‌شود</li>}
        </ul>
        <div className="row">
          <button className="btn primary" onClick={() => navigate("/")}>
            بازگشت به جلسه‌ها
          </button>
          <button className="btn" onClick={() => navigate("/meetings/m4")}>
            مشاهدهٔ جلسهٔ در حال پردازش
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="grid-2">
      <div>
        <div className="card">
          <div className="row between">
            <div className="row">
              <span className="live-dot" />
              <strong>{title}</strong>
            </div>
            <div className="row">
              <div className="vu">
                <span /><span /><span /><span /><span />
              </div>
              <span className="clock ltr">{d(formatClock(elapsed))}</span>
            </div>
          </div>
          {mode === "room_mic" && enrollment && captions.length === 0 && (
            <p className="badge warn" style={{ marginTop: 10 }}>
              دور معارفه: هر نفر یک جمله خودش را معرفی کند 🎤
            </p>
          )}
          <div className="captions" ref={captionsRef}>
            {captions.length === 0 && (
              <p className="muted">در انتظار گفتار… (کپشن زنده با ~۲ تا ۵ ثانیه تأخیر)</p>
            )}
            {captions.map((c, i) => (
              <div
                key={i}
                className={"caption-line" + (i === captions.length - 1 ? " latest" : "")}
              >
                {c}
              </div>
            ))}
          </div>
          <p className="muted small" style={{ marginBottom: 0 }}>
            کپشن زنده تقریبی است؛ رونوشت نهایی با کیفیت کامل و برچسب گوینده پس از پایان جلسه
            جایگزین می‌شود.
          </p>
        </div>

        <div className="card">
          <div className="row between">
            <div className="row wrap">
              <button className="btn" onClick={addBookmark} title="Ctrl+B">
                🔖 علامت بزن
              </button>
              <span className="muted small">
                میان‌بر: <span className="kbd ltr">Ctrl+B</span>
              </span>
            </div>
            <button
              className="btn danger"
              onClick={() => {
                if (window.confirm("جلسه پایان یابد؟ گذر کیفیت بلافاصله شروع می‌شود.")) {
                  setPhase("ended");
                }
              }}
            >
              ■ پایان جلسه
            </button>
          </div>
          {bookmarks.length > 0 && (
            <div className="row wrap" style={{ marginTop: 10 }}>
              {bookmarks.map((b, i) => (
                <span key={i} className="badge warn">
                  🔖 {d(formatClock(b.at_s))}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="card">
        <h3>📝 دفترچهٔ جلسه</h3>
        <p className="muted small">
          یادداشت‌های خام شما با مُهر زمانی ذخیره می‌شود؛ بعد از جلسه، دستیار آن‌ها را با
          رونوشت ادغام می‌کند و صورتجلسه‌ای می‌سازد که خودتان در نوشتنش سهیم بوده‌اید.
        </p>
        <textarea
          className="input"
          style={{ minHeight: 260 }}
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder="یادداشت بنویسید…"
        />
      </div>
    </div>
  );
}
