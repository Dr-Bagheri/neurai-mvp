import { useEffect, useState } from "react";
import { api } from "../api/client";
import type {
  AuditEntry,
  ConnectivityProfile,
  DiskHealth,
  ErrorLogEntry,
  ModelStatus,
  QueueJob,
  RetentionSettings,
} from "../api/types";
import { ProvenanceBadge } from "../components/ProvenanceBadge";
import { formatJalaliShort } from "../lib/jalali";
import { formatTimeOfDay } from "../lib/time";
import { useApp } from "../state/AppContext";

const JOB_LABEL: Record<QueueJob["status"], { text: string; cls: string }> = {
  running: { text: "در حال اجرا", cls: "warn" },
  queued: { text: "در صف", cls: "plain" },
  done: { text: "تمام شد", cls: "ok" },
};

export function AdminPage() {
  const { d, status, refreshStatus } = useApp();
  const [queue, setQueue] = useState<QueueJob[]>([]);
  const [audit, setAudit] = useState<AuditEntry[]>([]);
  const [disk, setDisk] = useState<DiskHealth | null>(null);
  const [models, setModels] = useState<ModelStatus[]>([]);
  const [errors, setErrors] = useState<ErrorLogEntry[]>([]);
  const [retention, setRetention] = useState<RetentionSettings | null>(null);

  useEffect(() => {
    void api.listQueue().then(setQueue);
    void api.listAudit().then(setAudit);
    void api.getDiskHealth().then(setDisk);
    void api.listModels().then(setModels);
    void api.listErrors().then(setErrors);
    void api.getRetention().then(setRetention);
  }, []);

  const saveRetention = async (patch: Partial<RetentionSettings>) => {
    if (!retention) return;
    setRetention(await api.setRetention({ ...retention, ...patch }));
  };

  const setProfile = async (p: ConnectivityProfile) => {
    await api.setProfile(p);
    await refreshStatus();
  };

  const setCloud = async (enabled: boolean) => {
    await api.setWorkspaceCloud(enabled);
    await refreshStatus();
  };

  if (!status) return <p className="muted">در حال بارگذاری…</p>;

  return (
    <>
      <div className="grid-2">
        <div className="card">
          <h3>پروفایل اتصال سرور</h3>
          <p className="muted small">
            «ایزوله» تمام مسیرهای ابری را در سطح کد غیرفعال می‌کند — نه پروب شبکه، نه
            تله‌متری. «خودکار» فقط در صورت رضایتِ فضای کاری از ابر استفاده می‌کند و هنگام قطع
            شبکه بی‌صدا به مدل محلی برمی‌گردد.
          </p>
          <div className="row wrap" style={{ marginBottom: 12 }}>
            <button
              className={"btn" + (status.profile === "auto" ? " primary" : "")}
              onClick={() => void setProfile("auto")}
            >
              🌐 خودکار
            </button>
            <button
              className={"btn" + (status.profile === "air_gapped" ? " primary" : "")}
              onClick={() => void setProfile("air_gapped")}
            >
              ⛔ ایزوله (Air-gapped)
            </button>
          </div>
          <label className="row">
            <input
              type="checkbox"
              checked={status.cloud_enabled_workspace}
              disabled={status.profile === "air_gapped"}
              onChange={(e) => void setCloud(e.target.checked)}
            />
            فعال‌سازی مدل ابری برای این فضای کاری (هر جلسه جداگانه هم قابل قفل به «فقط
            محلی» است)
          </label>
          <p className="muted small" style={{ marginBottom: 0 }}>
            صدا در هیچ حالتی از سرور خارج نمی‌شود؛ ابر فقط برای کارهای متنی و با رضایت است.
          </p>
        </div>

        <div className="card">
          <h3>وضعیت سرور</h3>
          <div className="stat">
            <span className="muted small">حافظهٔ در حال استفاده</span>
            <span className="value">
              {d(status.ram_used_gb)} <span className="small muted">از {d(status.ram_total_gb)} گیگابایت</span>
            </span>
          </div>
          <div className="progress" style={{ margin: "6px 0 14px" }}>
            <div
              className="fill"
              style={{ width: `${(status.ram_used_gb / status.ram_total_gb) * 100}%` }}
            />
          </div>
          <p className="muted small" style={{ marginBottom: 0 }}>
            ظرفیت: {d(1)} جلسهٔ زندهٔ هم‌زمان (سقف پیکربندی). جلسهٔ زنده همیشه اولویت دارد؛
            گذر کیفیت و کارهای مدل زبانی در صف اجرا می‌شوند.
          </p>
        </div>
      </div>

      <div className="grid-2" style={{ marginTop: 16 }}>
        <div className="card">
          <h3>فضای دیسک</h3>
          {disk && (
            <>
              <div className="stat">
                <span className="muted small">استفاده‌شده</span>
                <span className="value">
                  {d(disk.used_gb)}{" "}
                  <span className="small muted">از {d(disk.total_gb)} گیگابایت</span>
                </span>
              </div>
              <div className="progress" style={{ margin: "6px 0 10px" }}>
                <div className="fill" style={{ width: `${(disk.used_gb / disk.total_gb) * 100}%` }} />
              </div>
              <p className="muted small" style={{ marginBottom: 0 }}>
                سهم فایل‌های صوتی: {d(disk.audio_gb)} گیگابایت · با نرخ رشد فعلی، دیسک حدود{" "}
                <strong>{d(disk.projected_full_days)} روز</strong> دیگر پر می‌شود. سیاست
                نگهداری را در همین صفحه تنظیم کنید.
              </p>
            </>
          )}
        </div>

        <div className="card">
          <h3>سیاست نگهداری داده</h3>
          {retention && (
            <>
              <label className="small muted">نگهداری فایل صوتی (روز — ۰ یعنی برای همیشه)</label>
              <input
                className="input ltr"
                type="number"
                min={0}
                value={retention.audio_days}
                onChange={(e) => void saveRetention({ audio_days: Number(e.target.value) })}
                style={{ marginBottom: 10, maxWidth: 140 }}
              />
              <label className="small muted">نگهداری رونوشت (روز — ۰ یعنی تا حذف دستی)</label>
              <input
                className="input ltr"
                type="number"
                min={0}
                value={retention.transcript_days}
                onChange={(e) => void saveRetention({ transcript_days: Number(e.target.value) })}
                style={{ maxWidth: 140 }}
              />
              <p className="muted small" style={{ marginBottom: 0 }}>
                «حذف واقعی»: با حذف هر جلسه، رونوشت، صدا، بردارها و ورودی‌های جستجو با هم
                پاک می‌شوند.
              </p>
            </>
          )}
        </div>
      </div>

      <div className="card">
        <h3>وضعیت مدل‌ها</h3>
        <table className="table">
          <thead>
            <tr>
              <th>مدل</th>
              <th>نقش</th>
              <th>نسخه</th>
              <th>وضعیت</th>
            </tr>
          </thead>
          <tbody>
            {models.map((m) => (
              <tr key={m.name}>
                <td className="ltr">{m.name}</td>
                <td>{m.role}</td>
                <td className="ltr muted">{m.version}</td>
                <td>
                  {m.loaded ? (
                    <span className="badge ok">بارگذاری‌شده</span>
                  ) : (
                    <span className="badge plain">در حافظه نیست</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="muted small" style={{ marginBottom: 0 }}>
          به‌روزرسانی مدل‌ها از طریق «مدیر مدل»: دانلود آنلاین یا بستهٔ آفلاین امضاشده
          (USB) برای سرورهای ایزوله. هیچ داده‌ای هرگز از سرور ارسال نمی‌شود — بدون
          تله‌متری.
        </p>
      </div>

      <div className="card">
        <h3>آخرین خطاها</h3>
        {errors.length === 0 ? (
          <div className="empty">خطایی ثبت نشده است.</div>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>زمان</th>
                <th>بخش</th>
                <th>پیام</th>
              </tr>
            </thead>
            <tbody>
              {errors.map((e) => (
                <tr key={e.id}>
                  <td className="muted small">
                    {d(formatJalaliShort(new Date(e.at)))} — {d(formatTimeOfDay(new Date(e.at)))}
                  </td>
                  <td className="ltr">{e.source}</td>
                  <td>{e.message}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="card">
        <h3>صف پردازش</h3>
        <table className="table">
          <thead>
            <tr>
              <th>کار</th>
              <th>وضعیت</th>
              <th style={{ width: 180 }}>پیشرفت</th>
            </tr>
          </thead>
          <tbody>
            {queue.map((j) => (
              <tr key={j.id}>
                <td>{j.label}</td>
                <td>
                  <span className={`badge ${JOB_LABEL[j.status].cls}`}>
                    {JOB_LABEL[j.status].text}
                  </span>
                </td>
                <td>
                  <div className="progress">
                    <div className="fill" style={{ width: `${j.progress * 100}%` }} />
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card">
        <h3>گزارش ممیزی مهارت‌ها</h3>
        <p className="muted small">
          هر فراخوانی مهارت (چه کسی، کدام مهارت، کدام منبع، محلی یا ابری) در یک گزارش
          فقط-افزودنی ثبت می‌شود.
        </p>
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
                <td className="muted small">
                  {d(formatJalaliShort(new Date(a.at)))} — {d(formatTimeOfDay(new Date(a.at)))}
                </td>
                <td className="ltr">{a.username}</td>
                <td>
                  <span className="skill-chip">
                    🛠️ <span className="ltr">{a.skill}</span>
                  </span>
                </td>
                <td>{a.resource}</td>
                <td>
                  <ProvenanceBadge provenance={a.provenance} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
