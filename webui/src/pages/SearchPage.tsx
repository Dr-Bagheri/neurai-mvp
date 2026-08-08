import { useEffect, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, ApiError } from "../api/client";
import type { SearchHit } from "../api/types";
import { useApp } from "../state/AppContext";

export function SearchPage() {
  const { d } = useApp();
  const [params, setParams] = useSearchParams();
  const urlQuery = params.get("q") ?? "";
  const [query, setQuery] = useState(urlQuery);
  const [kind, setKind] = useState<"" | "transcript" | "document">("");
  const [hits, setHits] = useState<SearchHit[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const run = async (q: string, k: typeof kind) => {
    if (!q.trim()) return;
    setBusy(true);
    setError("");
    try {
      setHits(await api.search(q.trim(), k === "" ? undefined : k));
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "جستجو ممکن نشد");
    } finally {
      setBusy(false);
    }
  };

  // The global top-bar search lands here with ?q=… — run it immediately.
  useEffect(() => {
    setQuery(urlQuery);
    if (urlQuery.trim()) void run(urlQuery, "");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [urlQuery]);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;
    setParams({ q: query.trim() }, { replace: true });
    await run(query, kind);
  };

  return (
    <>
      <div className="card">
        <form className="row" onSubmit={submit}>
          <input
            className="input"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="جستجوی معنایی در رونوشت‌ها و اسناد… مثلاً: «بودجهٔ زیرساخت»"
            autoFocus
          />
          <select
            className="input"
            style={{ maxWidth: 160 }}
            value={kind}
            onChange={(e) => setKind(e.target.value as typeof kind)}
          >
            <option value="">همه</option>
            <option value="transcript">فقط جلسه‌ها</option>
            <option value="document">فقط اسناد</option>
          </select>
          <button className="btn primary" disabled={busy}>
            جستجو
          </button>
        </form>
        <p className="muted small" style={{ marginBottom: 0 }}>
          جستجو کاملاً محلی است و فقط جلسه‌ها و اسناد خودتان را می‌گردد؛ جلسه‌های «محرمانه»
          در نتایج نمی‌آیند.
        </p>
        {error && (
          <p className="badge danger" style={{ marginTop: 8 }}>
            {error}
          </p>
        )}
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
                  <span className="ts">{d((h.score * 100).toFixed(0))}٪</span>
                  <div>
                    <div>{h.text}</div>
                    <div className="muted small">
                      {h.kind === "transcript" ? (
                        <Link to={`/meetings/${h.ref_id}`}>جلسهٔ {d(h.ref_id)} ←</Link>
                      ) : (
                        <>سند {d(h.ref_id)}</>
                      )}
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
