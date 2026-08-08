/** The 🏠/☁️ badge every model response carries (D3). `source` comes from the
 * harness ("local" | "cloud"); anything unknown renders as local. */
export function ProvenanceBadge({ source }: { source: string }) {
  return source === "cloud" ? (
    <span className="badge cloud" title="پردازش با مدل ابری — با رضایت این فضای کاری">
      ☁️ ابری
    </span>
  ) : (
    <span className="badge local" title="پردازش کاملاً محلی — داده‌ای از سرور خارج نشده">
      🏠 محلی
    </span>
  );
}
