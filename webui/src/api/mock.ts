// In-browser mock of the NeurAI engine. The UI talks only to api/client.ts;
// this file supplies data until the FastAPI server exists.

import type {
  ActionItem,
  AuditEntry,
  ChatMessage,
  DiskHealth,
  DocumentInfo,
  ErrorLogEntry,
  Meeting,
  ModelStatus,
  QueueJob,
  RetentionSettings,
  SearchHit,
  ServerStatus,
  TranscriptSegment,
  User,
} from "./types";

export const MOCK_USER: User = {
  id: "u1",
  username: "sara",
  display_name: "سارا محمدی",
  is_admin: true,
  has_voice_profile: true,
};

const daysAgo = (n: number, h = 10, m = 0) => {
  const d = new Date();
  d.setDate(d.getDate() - n);
  d.setHours(h, m, 0, 0);
  return d.toISOString();
};

function seg(
  id: string,
  start: number,
  end: number,
  speaker: string | null,
  text: string,
  bookmarked = false,
): TranscriptSegment {
  return { id, start_s: start, end_s: end, speaker, text, bookmarked };
}

export const MOCK_MEETINGS: Meeting[] = [
  {
    id: "m1",
    title: "استندآپ هفتگی تیم محصول",
    started_at: daysAgo(1, 9, 30),
    duration_s: 2760,
    status: "ready",
    capture_mode: "room_mic",
    local_only: true,
    sensitivity: "normal",
    is_series: true,
    series_name: "استندآپ تیم محصول",
    participants: ["سارا محمدی", "امیر رضایی", "نگار کریمی", "حمید توکلی"],
    segments: [
      seg("s1", 12, 21, "سارا محمدی", "خب سلام به همه، جلسهٔ استندآپ این هفته رو شروع می‌کنیم. اول گزارش اسپرینت قبل رو مرور کنیم."),
      seg("s2", 22, 48, "امیر رضایی", "ماژول رونویسی زنده تقریباً تمومه. تأخیر کپشن‌ها روی سرور تست به زیر سه ثانیه رسیده و مدل کوچیک فارسی هم روی صدای واقعی جلسه جواب خوبی می‌ده."),
      seg("s3", 49, 74, "نگار کریمی", "من روی خروجی صورتجلسه کار کردم. قالب رسمی با حاضرین و غایبین و مصوبات آماده‌ست، فقط خروجی Word هنوز فونت رو درست embed نمی‌کنه.", true),
      seg("s4", 75, 96, "حمید توکلی", "دیتابیس برداری هم راه افتاده. جستجوی معنایی روی رونوشت‌ها با BGE-M3 تست شد، دقتش روی فارسی بهتر از انتظار بود."),
      seg("s5", 97, 128, "سارا محمدی", "عالیه. پس مصوبه این باشه: امیر تا آخر هفته تست بار رو روی سرور شانزده گیگ انجام بده، نگار مشکل فونت خروجی رو حل کنه، و حمید مستندات لایهٔ داده رو بنویسه."),
      seg("s6", 129, 151, "امیر رضایی", "قبوله. فقط یادمون باشه قبل از دمو، سناریوی قطع شبکه رو هم تمرین کنیم — باید نشون بدیم همه‌چیز آفلاین کار می‌کنه."),
      seg("s7", 152, 170, "نگار کریمی", "موافقم. برای دموی مشتری بانکی این مهم‌ترین بخشه."),
    ],
    bookmarks: [
      { id: "b1", at_s: 49, label: "مشکل فونت در خروجی Word" },
      { id: "b2", at_s: 97, label: "مصوبات جلسه" },
    ],
    notes: "- قبل از دمو: تمرین سناریوی آفلاین\n- پیگیری فونت وزیرمتن در خروجی Word\n- ایدهٔ نگار: قالب جداگانه برای جلسات تصمیم‌گیری",
    summary: {
      overview:
        "در استندآپ این هفته پیشرفت سه بخش اصلی مرور شد: رونویسی زنده به تأخیر زیر سه ثانیه رسیده، قالب صورتجلسهٔ رسمی آماده شده (به‌جز مشکل فونت در خروجی Word) و جستجوی معنایی فارسی روی لایهٔ داده تست شده است. تیم توافق کرد پیش از دموی مشتری، سناریوی قطع کامل شبکه تمرین شود.",
      decisions: [
        "تست بار روی سرور ۱۶ گیگابایتی تا پایان هفته انجام شود.",
        "مشکل embed فونت در خروجی Word پیش از دمو رفع شود.",
        "سناریوی قطع شبکه پیش از دموی مشتری تمرین شود.",
      ],
      provenance: "local",
    },
  },
  {
    id: "m2",
    title: "جلسهٔ تصمیم‌گیری بودجهٔ زیرساخت",
    started_at: daysAgo(6, 14, 0),
    duration_s: 4680,
    status: "ready",
    capture_mode: "per_participant",
    local_only: false,
    sensitivity: "normal",
    is_series: false,
    series_name: null,
    participants: ["سارا محمدی", "دکتر افشار", "امیر رضایی"],
    segments: [
      seg("s1", 30, 62, "دکتر افشار", "موضوع اصلی امروز تصمیم دربارهٔ سرور مشتریان سازمانیه. پیشنهاد این بود که برای استقرارهای بزرگ‌تر، پیکربندی با کارت گرافیک هم ارائه بدیم."),
      seg("s2", 63, 101, "سارا محمدی", "بر اساس معماری فعلی، خط پایهٔ ما شانزده گیگ بدون GPU هست و یک جلسهٔ زندهٔ هم‌زمان رو راحت جواب می‌ده. GPU فقط ظرفیت رو بالا می‌بره، تغییر معماری نمی‌خواد."),
      seg("s3", 102, 140, "امیر رضایی", "از نظر هزینه، اختلاف حدود چهل درصده. پیشنهاد من اینه که پکیج پایه رو همون بدون GPU نگه داریم و GPU رو به‌عنوان پلن ارتقا بفروشیم.", true),
      seg("s4", 141, 178, "دکتر افشار", "منطقیه. پس مصوبه: پکیج پایه بدون تغییر، پلن ارتقای GPU به پیشنهاد قیمت اضافه بشه. سارا تا جلسهٔ بعد سند مقایسهٔ ظرفیت رو آماده کنه."),
    ],
    bookmarks: [{ id: "b1", at_s: 102, label: "تحلیل هزینهٔ GPU" }],
    notes: "",
    summary: {
      overview:
        "جلسه دربارهٔ پیکربندی سخت‌افزاری پیشنهادی برای مشتریان سازمانی بود. تصمیم نهایی: بستهٔ پایه روی همان خط پایهٔ ۱۶ گیگابایت بدون GPU باقی می‌ماند و GPU به‌عنوان پلن ارتقا عرضه می‌شود.",
      decisions: [
        "بستهٔ پایه بدون GPU باقی بماند.",
        "پلن ارتقای GPU به پیشنهاد قیمت اضافه شود.",
        "سند مقایسهٔ ظرفیت تا جلسهٔ بعد آماده شود (سارا).",
      ],
      provenance: "cloud",
    },
  },
  {
    id: "m3",
    title: "استندآپ هفتگی تیم محصول",
    started_at: daysAgo(8, 9, 30),
    duration_s: 2400,
    status: "ready",
    capture_mode: "room_mic",
    local_only: true,
    sensitivity: "normal",
    is_series: true,
    series_name: "استندآپ تیم محصول",
    participants: ["سارا محمدی", "امیر رضایی", "نگار کریمی"],
    segments: [
      seg("s1", 15, 40, "سارا محمدی", "این هفته تمرکز روی خط لولهٔ صوت بود. امیر، وضعیت تشخیص گوینده چطوره؟"),
      seg("s2", 41, 80, "امیر رضایی", "مدل تفکیک گوینده روی ضبط‌های واقعی تست شد. روی میکروفون اتاق با سه نفر خطا کمه، ولی وقتی صحبت‌ها هم‌پوشانی داره هنوز اشتباه می‌کنه."),
      seg("s3", 81, 110, "نگار کریمی", "برای دور معارفه هم پیشنهاد دارم اول هر جلسه هر نفر یک جمله خودش رو معرفی کنه تا اثر صدا ثبت بشه."),
    ],
    bookmarks: [],
    notes: "",
    summary: {
      overview:
        "مرور پیشرفت خط لولهٔ صوت: تفکیک گوینده روی ضبط واقعی تست شد و برای بهبود شناسایی، دور معارفهٔ ابتدای جلسه پیشنهاد شد.",
      decisions: ["دور معارفه در ابتدای جلسات اتاق اضافه شود."],
      provenance: "local",
    },
  },
  {
    id: "m4",
    title: "بررسی قرارداد مشتری — در حال پردازش",
    started_at: daysAgo(0, 11, 15),
    duration_s: 1980,
    status: "processing",
    capture_mode: "room_mic",
    local_only: true,
    sensitivity: "confidential",
    is_series: false,
    series_name: null,
    participants: ["سارا محمدی", "حمید توکلی"],
    segments: [
      seg("s1", 8, 30, null, "خب این نسخهٔ جدید قرارداد رو با هم مرور کنیم بند به بند..."),
      seg("s2", 31, 55, null, "بند محرمانگی داده‌ها باید صریح بگه که هیچ داده‌ای از سرور خارج نمی‌شه."),
    ],
    bookmarks: [],
    notes: "",
    summary: null,
  },
];

export const MOCK_ACTION_ITEMS: ActionItem[] = [
  {
    id: "a1",
    meeting_id: "m1",
    meeting_title: "استندآپ هفتگی تیم محصول",
    text: "انجام تست بار روی سرور ۱۶ گیگابایتی",
    assignee: "امیر رضایی",
    due_date: daysAgo(-4),
    status: "in_progress",
  },
  {
    id: "a2",
    meeting_id: "m1",
    meeting_title: "استندآپ هفتگی تیم محصول",
    text: "رفع مشکل embed فونت در خروجی Word صورتجلسه",
    assignee: "نگار کریمی",
    due_date: daysAgo(-2),
    status: "open",
  },
  {
    id: "a3",
    meeting_id: "m1",
    meeting_title: "استندآپ هفتگی تیم محصول",
    text: "نوشتن مستندات لایهٔ داده",
    assignee: "حمید توکلی",
    due_date: null,
    status: "open",
  },
  {
    id: "a4",
    meeting_id: "m2",
    meeting_title: "جلسهٔ تصمیم‌گیری بودجهٔ زیرساخت",
    text: "تهیهٔ سند مقایسهٔ ظرفیت پایه در برابر GPU",
    assignee: "سارا محمدی",
    due_date: daysAgo(-1),
    status: "in_progress",
  },
  {
    id: "a5",
    meeting_id: "m3",
    meeting_title: "استندآپ هفتگی تیم محصول",
    text: "افزودن دور معارفه به ابتدای جلسات اتاق",
    assignee: "امیر رضایی",
    due_date: daysAgo(2),
    status: "done",
  },
];

export const MOCK_DOCUMENTS: DocumentInfo[] = [
  { id: "d1", name: "قرارداد نمونهٔ مشتری سازمانی.pdf", pages: 18, indexed_at: daysAgo(3) },
  { id: "d2", name: "معماری NeurAI نسخهٔ ۰.۲.pdf", pages: 12, indexed_at: daysAgo(5) },
  { id: "d3", name: "راهنمای استقرار سرور ویندوز.docx", pages: 24, indexed_at: daysAgo(9) },
];

export const MOCK_QUEUE: QueueJob[] = [
  { id: "q1", kind: "quality_pass", label: "گذر کیفیت — بررسی قرارداد مشتری", status: "running", progress: 0.62 },
  { id: "q2", kind: "summary", label: "خلاصه‌سازی — بررسی قرارداد مشتری", status: "queued", progress: 0 },
  { id: "q3", kind: "embedding", label: "نمایه‌سازی سند — راهنمای استقرار", status: "done", progress: 1 },
];

export const MOCK_AUDIT: AuditEntry[] = [
  { id: "l1", at: daysAgo(0, 12, 4), username: "sara", skill: "summarize_meeting", resource: "جلسهٔ m1", provenance: "local" },
  { id: "l2", at: daysAgo(0, 11, 48), username: "amir", skill: "search_transcripts", resource: "«مهلت قرارداد»", provenance: "local" },
  { id: "l3", at: daysAgo(1, 16, 20), username: "sara", skill: "export_minutes", resource: "صورتجلسهٔ m2 (Word)", provenance: "local" },
  { id: "l4", at: daysAgo(1, 15, 2), username: "negar", skill: "translate", resource: "خلاصهٔ m2 → انگلیسی", provenance: "cloud" },
];

export const MOCK_DISK: DiskHealth = {
  used_gb: 182,
  total_gb: 512,
  audio_gb: 96,
  projected_full_days: 210,
};

export const MOCK_MODELS: ModelStatus[] = [
  { name: "faster-whisper small (fa)", role: "رونویسی زنده", version: "int8", loaded: true },
  { name: "whisper-large-fa-v1", role: "گذر کیفیت", version: "int8", loaded: true },
  { name: "Qwen3-8B q4", role: "مدل زبانی محلی", version: "q4_K_M", loaded: true },
  { name: "BGE-M3", role: "بردارسازی (RAG)", version: "1.5", loaded: true },
  { name: "3D-Speaker ECAPA", role: "تفکیک/شناسایی گوینده", version: "0.9", loaded: false },
];

export const MOCK_ERRORS: ErrorLogEntry[] = [
  {
    id: "e1",
    at: daysAgo(0, 8, 12),
    source: "quality_pass",
    message: "بارگذاری مدل تفکیک گوینده کند بود (۴۱ ثانیه) — احتمال کمبود حافظه هنگام اجرای هم‌زمان.",
  },
  {
    id: "e2",
    at: daysAgo(2, 17, 40),
    source: "harness",
    message: "فراخوانی ابری پس از ۲۰ ثانیه timeout شد؛ به مدل محلی برگشت (پاسخ 🏠 تحویل شد).",
  },
];

export const MOCK_RETENTION: RetentionSettings = {
  audio_days: 90,
  transcript_days: 0,
};

export const MOCK_STATUS: ServerStatus = {
  online: true,
  profile: "auto",
  cloud_enabled_workspace: false,
  live_meeting_id: null,
  ram_used_gb: 9.4,
  ram_total_gb: 16,
};

export const MOCK_CHAT_SEED: ChatMessage[] = [
  {
    id: "c1",
    role: "assistant",
    text: "سلام سارا! من دستیار NeurAI هستم. می‌تونم جلسه‌ها رو خلاصه کنم، توی رونوشت‌ها بگردم، کارهای باز رو نشون بدم یا به سؤال‌هات از روی اسناد جواب بدم.",
    provenance: "local",
  },
];

// Live-caption feed for the live meeting simulation.
export const LIVE_CAPTION_FEED: string[] = [
  "خب، فکر می‌کنم همه اومدن، شروع کنیم.",
  "دستور جلسهٔ امروز بررسی نتایج تست مدل فارسی روی صدای واقعی جلسه‌ست.",
  "نرخ خطای کلمه روی میکروفون اتاق حدود هجده درصد اندازه‌گیری شد.",
  "البته وقتی فاصله از میکروفون زیاد می‌شه، خطا هم بالا می‌ره.",
  "پیشنهاد می‌کنم برای اتاق‌های بزرگ دو تا میکروفون توصیه کنیم.",
  "بخش دوم، تبدیل گفتاری به نوشتاری برای صورتجلسه‌ست.",
  "مدل محلی جمله‌های محاوره‌ای رو خوب رسمی می‌کنه ولی روی اصطلاحات فنی انگلیسی گاهی اشتباه می‌کنه.",
  "این مورد رو به مجموعهٔ ارزیابی اضافه می‌کنیم تا در CI سنجیده بشه.",
  "خیلی خب، جمع‌بندی کنیم و مصوبات رو ثبت کنیم.",
];

// Canned skill-driven chat answers for the demo assistant.
export interface CannedAnswer {
  match: RegExp;
  build: () => Omit<ChatMessage, "id" | "role">;
}

export const CANNED_ANSWERS: CannedAnswer[] = [
  {
    match: /خلاصه|جمع‌بندی|summary/i,
    build: () => ({
      text:
        "خلاصهٔ جلسهٔ دیروز (استندآپ هفتگی تیم محصول):\n\n" +
        "رونویسی زنده به تأخیر زیر ۳ ثانیه رسیده، قالب صورتجلسهٔ رسمی آماده شده (به‌جز مشکل فونت در خروجی Word) و جستجوی معنایی فارسی تست شده است. تیم توافق کرد پیش از دموی مشتری، سناریوی قطع کامل شبکه تمرین شود.\n\n" +
        "مصوبات: تست بار روی سرور ۱۶ گیگ (امیر)، رفع مشکل فونت (نگار)، مستندات لایهٔ داده (حمید).",
      provenance: "local",
      skill_calls: [
        { skill: "list_meetings", args: { range: "دیروز" }, side_effect: false },
        { skill: "summarize_meeting", args: { meeting: "استندآپ هفتگی تیم محصول" }, side_effect: false },
      ],
      citations: [
        {
          kind: "meeting",
          ref_id: "m1",
          title: "استندآپ هفتگی تیم محصول",
          snippet: "پس مصوبه این باشه: امیر تا آخر هفته تست بار رو…",
        },
      ],
    }),
  },
  {
    match: /کار|اکشن|action|وظایف/i,
    build: () => ({
      text:
        "کارهای باز فعلی:\n\n" +
        "۱. تست بار روی سرور ۱۶ گیگ — امیر رضایی (در حال انجام)\n" +
        "۲. رفع مشکل فونت خروجی Word — نگار کریمی (باز)\n" +
        "۳. مستندات لایهٔ داده — حمید توکلی (باز)\n" +
        "۴. سند مقایسهٔ ظرفیت — سارا محمدی (در حال انجام)",
      provenance: "local",
      skill_calls: [{ skill: "list_open_action_items", args: {}, side_effect: false }],
      citations: [
        { kind: "meeting", ref_id: "m1", title: "استندآپ هفتگی تیم محصول", snippet: "مصوبات جلسه" },
        { kind: "meeting", ref_id: "m2", title: "جلسهٔ تصمیم‌گیری بودجهٔ زیرساخت", snippet: "سارا تا جلسهٔ بعد سند مقایسهٔ ظرفیت رو آماده کنه" },
      ],
    }),
  },
  {
    match: /بودجه|GPU|سرور|قیمت/i,
    build: () => ({
      text:
        "دربارهٔ بودجهٔ زیرساخت، در جلسهٔ «تصمیم‌گیری بودجهٔ زیرساخت» تصمیم گرفته شد بستهٔ پایه روی ۱۶ گیگابایت بدون GPU بماند و GPU به‌عنوان پلن ارتقا فروخته شود (اختلاف هزینه حدود ۴۰٪).",
      provenance: "local",
      skill_calls: [
        { skill: "search_transcripts", args: { query: "بودجه GPU" }, side_effect: false },
        { skill: "get_transcript", args: { meeting: "m2" }, side_effect: false },
      ],
      citations: [
        {
          kind: "meeting",
          ref_id: "m2",
          title: "جلسهٔ تصمیم‌گیری بودجهٔ زیرساخت",
          snippet: "پکیج پایه رو همون بدون GPU نگه داریم و GPU رو به‌عنوان پلن ارتقا بفروشیم",
        },
      ],
    }),
  },
  {
    match: /خروجی|export|صورتجلسه|word|pdf/i,
    build: () => ({
      text: "می‌توانم صورتجلسهٔ رسمی جلسهٔ «تصمیم‌گیری بودجهٔ زیرساخت» را با قالب رسمی (حاضرین، دستور جلسه، مصوبات، محل امضا) به Word خروجی بدهم. چون این یک عمل دارای اثر جانبی است، نیاز به تأیید شما دارد.",
      provenance: "local",
      skill_calls: [{ skill: "get_transcript", args: { meeting: "m2" }, side_effect: false }],
      pending_confirmation: {
        skill: "export_minutes",
        args: { meeting: "جلسهٔ تصمیم‌گیری بودجهٔ زیرساخت", format: "Word (صورتجلسهٔ رسمی)" },
        side_effect: true,
      },
    }),
  },
];

export const FALLBACK_ANSWER = (): Omit<ChatMessage, "id" | "role"> => ({
  text:
    "در حالت نمایشی، من به موتور واقعی متصل نیستم و فقط چند سناریوی نمونه را پاسخ می‌دهم. " +
    "می‌توانید بپرسید: «جلسه دیروز رو خلاصه کن»، «کارهای باز چیه؟»، «درباره بودجه چی تصمیم گرفتیم؟» یا «صورتجلسه رو خروجی بگیر».",
  provenance: "local",
});

export const MOCK_SEARCH = (query: string): SearchHit[] => {
  const hits: SearchHit[] = [];
  for (const m of MOCK_MEETINGS) {
    // «محرمانه» meetings are excluded from cross-meeting search (D4).
    if (m.sensitivity === "confidential") continue;
    for (const s of m.segments) {
      if (query.trim() && s.text.includes(query.trim())) {
        hits.push({
          meeting_id: m.id,
          meeting_title: m.title,
          started_at: m.started_at,
          segment: s,
        });
      }
    }
  }
  return hits;
};
