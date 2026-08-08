import type { Provenance } from "../api/types";

/** The 🏠/☁️ badge every model response carries (D3). */
export function ProvenanceBadge({ provenance }: { provenance: Provenance }) {
  return provenance === "local" ? (
    <span className="badge local" title="پردازش کاملاً محلی — داده‌ای از سرور خارج نشده">
      🏠 محلی
    </span>
  ) : (
    <span className="badge cloud" title="پردازش با مدل ابری — با رضایت این فضای کاری">
      ☁️ ابری
    </span>
  );
}
