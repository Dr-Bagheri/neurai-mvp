import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { SearchHit } from "../api/types";
import { formatJalali } from "../lib/jalali";
import { formatClock } from "../lib/time";
import { useApp } from "../state/AppContext";

export function SearchPage() {
  const { d } = useApp();
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<SearchHit[] | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;
    setBusy(true);
    setHits(await api.searchTranscripts(query));
    setBusy(false);
  };

  return (
    <>
      <div className="card">
        <form className="row" onSubmit={submit}>
          <input
            className="input"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="جستجو در رونوشت همهٔ جلسه‌ها… مثلاً: «فونت» یا «GPU»"
            autoFocus
          />
          <button className="btn primary" disabled={busy}>
            جستجو
          </button>
        </form>
        <p className="muted small" style={{ marginBottom: 0 }}>
          جستجو کاملاً محلی است (جستجوی معنایی + واژه‌ای روی سرور دفتر). فقط جلسه‌هایی که به
          آن‌ها دسترسی دارید جستجو می‌شوند.
        </p>
      </div>

      {hits !== null && (
        <div className="card">
          {hits.length === 0 ? (
            <div className="empty">نتیجه‌ای پیدا نشد.</div>
          ) : (
            <>
              <p className="muted small">{d(hits.length)} نتیجه</p>
              {hits.map((h, i) => (
                <div key={i} className="segment" style={{ cursor: "default" }}>
                  <span className="ts">{d(formatClock(h.segment.start_s))}</span>
                  <div>
                    <div>
                      {h.segment.speaker && (
                        <span className="speaker">{h.segment.speaker}:</span>
                      )}
                      {h.segment.text}
                    </div>
                    <div className="muted small">
                      <Link to={`/meetings/${h.meeting_id}`}>{h.meeting_title}</Link> ·{" "}
                      {d(formatJalali(new Date(h.started_at)))}
                    </div>
                  </div>
                </div>
              ))}
            </>
          )}
        </div>
      )}
    </>
  );
}
