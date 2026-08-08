import type { MeetingStatus } from "../api/types";

export function MeetingStatusBadge({ status }: { status: MeetingStatus }) {
  switch (status) {
    case "live":
      return <span className="badge danger">● در حال ضبط</span>;
    case "processing":
      return <span className="badge warn">در حال پردازش گذر کیفیت…</span>;
    case "ready":
      return <span className="badge ok">آمادهٔ نهایی</span>;
  }
}

export function CaptureModeBadge({ mode }: { mode: "per_participant" | "room_mic" }) {
  return mode === "room_mic" ? (
    <span className="badge plain">🎙️ میکروفون اتاق</span>
  ) : (
    <span className="badge plain">👥 میکروفون هر شرکت‌کننده</span>
  );
}

export function LocalOnlyBadge({ localOnly }: { localOnly: boolean }) {
  return localOnly ? (
    <span className="badge local" title="این جلسه فقط با مدل‌های محلی پردازش می‌شود">
      🔒 فقط محلی
    </span>
  ) : null;
}

/** D4 sensitivity level: excluded from cross-meeting search and backups, local-only forever. */
export function ConfidentialBadge({ sensitivity }: { sensitivity: "normal" | "confidential" }) {
  return sensitivity === "confidential" ? (
    <span
      className="badge danger"
      title="محرمانه: برای همیشه فقط محلی؛ از جستجوی بین‌جلسه‌ای و پشتیبان‌گیری خارج است و فقط برای افراد مشخص‌شده قابل مشاهده است"
    >
      🛡️ محرمانه
    </span>
  ) : null;
}
