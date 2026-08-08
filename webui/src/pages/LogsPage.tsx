// گزارش‌ها (v0.3 UI restructure): job queue + skill audit + D12 security
// chain, moved out of server management (which keeps settings only).
import { useEffect, useState } from "react";
import { api, ApiError } from "../api/client";
import type { AuditFileRecord, AuditRow, AuditVerifyResult, JobRow } from "../api/types";
import { ProvenanceBadge } from "../components/ProvenanceBadge";
import { formatJalaliShort } from "../lib/jalali";
import { formatTimeOfDay } from "../lib/time";
import { useApp } from "../state/AppContext";
import { useChat } from "../state/ChatContext";

const JOB_LABEL: Record<string, { text: string; cls: string }> = {
  running: { text: "در حال اجرا", cls: "warn" },
  queued: { text: "در صف", cls: "plain" },
  done: { text: "تمام شد", cls: "ok" },
  failed: { text: "ناموفق", cls: "danger" },
};

const JOB_KIND_FA: Record<string, string> = {
  quality_pass: "آماده‌سازی رونوشت",
  summarize: "خلاصه‌سازی",
  index_document: "نمایه‌سازی سند",
  backup_snapshot: "پشتیبان‌گیری ابری",
};

const D12_ACTION_FA: Record<string, string> = {
  genesis: "شروع زنجیره",
  meeting_removed: "حذف جلسه",
  document_removed: "حذف سند",
  settings_changed: "تغییر تنظیمات",
  user_created: "ساخت کاربر",
};

function stamp(iso: string, d: (x: string | number) => string): string {
  const date = new Date(iso.includes("T") ? iso : iso.replace(" ", "T") + "Z");
  return `${d(formatJalaliShort(date))} — ${d(formatTimeOfDay(date))}`;
}

export function LogsPage() {
  const { d } = useApp();
  const { mutationCounter } = useChat();
  const [jobs, setJobs] = useState<JobRow[]>([]);
  const [audit, setAudit] = useState<AuditRow[]>([]);
  const [chain, setChain] = useState<AuditFileRecord[]>([]);
  const [chainVerify, setChainVerify] = useState<AuditVerifyResult | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    void Promise.all([
      api.adminJobs(),
      api.adminAudit(),
      api.adminAuditFile(),
      api.adminAuditVerify(),
    ])
      .then(([j, a, records, verify]) => {
        setJobs(j);
        setAudit(a);
        setChain(records.slice().reverse()); // newest first
        setChainVerify(verify);
      })
      .catch((e) => setError(e instanceof ApiError ? e.detail : "خطا در بارگذاری"));
  }, [mutationCounter]);

  if (error) return <p className="badge danger">{error}</p>;

  return (
    <>
      <div className="card">
        <h3>صف پردازش</h3>
        {jobs.length === 0 ? (
          <div className="empty">کاری در صف نیست.</div>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>کار</th>
                <th>وضعیت</th>
                <th style={{ width: 160 }}>پیشرفت</th>
                <th>ایجاد</th>
                <th>خطا</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((j) => {
                const st = JOB_LABEL[j.status] ?? { text: j.status, cls: "plain" };
                const pct =
                  j.status === "done" ? 100 : typeof j.progress === "number" ? j.progress : 0;
                return (
                  <tr key={j.id}>
                    <td>{JOB_KIND_FA[j.kind] ?? j.kind}</td>
                    <td>
                      <span className={`badge ${st.cls}`}>{st.text}</span>
                    </td>
                    <td>
                      <div className="row">
                        <div className="progress" style={{ flex: 1 }}>
                          <div className="fill" style={{ width: `${pct}%` }} />
                        </div>
                        {j.status === "running" && (
                          <span className="muted small ltr">٪{d(pct)}</span>
                        )}
                      </div>
                    </td>
                    <td className="muted small">{stamp(j.created_at, d)}</td>
                    <td className="muted small">{j.error ?? "—"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      <div className="card">
        <h3>گزارش امنیتی (زنجیرهٔ ممیزی — D12)</h3>
        {chainVerify &&
          (chainVerify.intact ? (
            <p className="badge ok" style={{ marginBottom: 10 }}>
              ✓ زنجیره سالم است — {d(chainVerify.records)} رکورد تأیید شد
            </p>
          ) : (
            <p className="badge danger" style={{ marginBottom: 10 }}>
              ✗ زنجیره شکسته است — خط {d(chainVerify.broken_at_line ?? 0)}: این فایل
              دست‌کاری شده یا خراب است
            </p>
          ))}
        <p className="muted small">
          رویدادهای امنیتی مدیر (به‌ویژه حذف‌ها) در یک فایل زنجیرهٔ درهم‌سازی ثبت می‌شوند؛
          هر ویرایش یا حذف خط، زنجیره را می‌شکند. فقط-خواندنی — هیچ API آن را تغییر
          نمی‌دهد.
        </p>
        {chain.length === 0 ? (
          <div className="empty">هنوز رویدادی ثبت نشده است.</div>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>زمان</th>
                <th>مدیر</th>
                <th>رویداد</th>
                <th>جزئیات</th>
              </tr>
            </thead>
            <tbody>
              {chain.slice(0, 50).map((r) => (
                <tr key={r.hash}>
                  <td className="muted small">{stamp(r.ts, d)}</td>
                  <td className="ltr">{r.actor}</td>
                  <td>
                    <span
                      className={`badge ${/removed|deleted/.test(r.action) ? "danger" : "plain"}`}
                    >
                      {D12_ACTION_FA[r.action] ?? r.action}
                    </span>
                  </td>
                  <td
                    className="muted small ltr"
                    style={{ maxWidth: 300, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
                  >
                    {JSON.stringify(r.details)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="card">
        <h3>گزارش ممیزی مهارت‌ها</h3>
        <p className="muted small">
          هر فراخوانی مهارت (چه کسی، کدام مهارت، کدام منبع، محلی یا ابری) در گزارش
          فقط-افزودنی ثبت می‌شود.
        </p>
        {audit.length === 0 ? (
          <div className="empty">هنوز فراخوانی‌ای ثبت نشده است.</div>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>زمان</th>
                <th>کاربر</th>
                <th>مهارت</th>
                <th>منبع</th>
                <th>پردازش</th>
              </tr>
            </thead>
            <tbody>
              {audit.map((a) => (
                <tr key={a.id}>
                  <td className="muted small">{stamp(a.created_at, d)}</td>
                  <td className="ltr">{a.username ?? d(a.user_id)}</td>
                  <td>
                    <span className="skill-chip">
                      🛠️ <span className="ltr">{a.skill}</span>
                    </span>
                    {!a.ok && <span className="badge danger">خطا</span>}
                  </td>
                  <td>{a.resource || "—"}</td>
                  <td>
                    <ProvenanceBadge source={a.source} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}
