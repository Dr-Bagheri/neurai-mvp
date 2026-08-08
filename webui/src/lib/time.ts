/** Seconds → "m:ss" or "h:mm:ss" for timestamps and durations. */
export function formatClock(totalSeconds: number): string {
  const s = Math.max(0, Math.floor(totalSeconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  const p = (n: number) => String(n).padStart(2, "0");
  return h > 0 ? `${h}:${p(m)}:${p(sec)}` : `${m}:${p(sec)}`;
}

/** Duration in Persian words: «۱ ساعت و ۲۰ دقیقه». Digits localized by caller setting. */
export function formatDurationFa(totalSeconds: number): string {
  const m = Math.round(totalSeconds / 60);
  const h = Math.floor(m / 60);
  const rem = m % 60;
  if (h > 0 && rem > 0) return `${h} ساعت و ${rem} دقیقه`;
  if (h > 0) return `${h} ساعت`;
  return `${m} دقیقه`;
}

export function formatTimeOfDay(date: Date): string {
  const p = (n: number) => String(n).padStart(2, "0");
  return `${p(date.getHours())}:${p(date.getMinutes())}`;
}
