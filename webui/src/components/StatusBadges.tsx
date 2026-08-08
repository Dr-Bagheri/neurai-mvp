import type { CaptureMode, MeetingStatus, Sensitivity } from "../api/types";

export function MeetingStatusBadge({ status }: { status: MeetingStatus | string }) {
  switch (status) {
    case "created":
      return <span className="badge plain">آمادهٔ شروع</span>;
    case "live":
      return <span className="badge danger">● در حال ضبط</span>;
    case "processing":
      return <span className="badge warn">در حال پردازش گذر کیفیت…</span>;
    case "done":
      return <span className="badge ok">آمادهٔ نهایی</span>;
    case "failed":
      return <span className="badge danger">پردازش ناموفق</span>;
    default:
      return <span className="badge plain">{status}</span>;
  }
}

export function CaptureModeBadge({ mode }: { mode: CaptureMode | string }) {
  return mode === "room" ? (
    <span className="badge plain">🎙️ میکروفون اتاق</span>
  ) : (
    <span className="badge plain">👥 میکروفون هر شرکت‌کننده</span>
  );
}

/** allow_cloud=false → the whole meeting is processed locally (D3). */
export function LocalOnlyBadge({ allowCloud }: { allowCloud: boolean }) {
  return allowCloud ? null : (
    <span className="badge local" title="این جلسه فقط با مدل‌های محلی پردازش می‌شود">
      🔒 فقط محلی
    </span>
  );
}

/** D4 sensitivity level: excluded from cross-meeting search and backups, local-only forever. */
export function ConfidentialBadge({ sensitivity }: { sensitivity: Sensitivity | string }) {
  return sensitivity === "confidential" ? (
    <span
      className="badge danger"
      title="محرمانه: برای همیشه فقط محلی؛ از جستجوی بین‌جلسه‌ای و پشتیبان‌گیری خارج است"
    >
      🛡️ محرمانه
    </span>
  ) : null;
}
