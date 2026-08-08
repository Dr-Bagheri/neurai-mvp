// Jalali (Shamsi) calendar conversion — pure arithmetic, no dependency.
// Algorithm: standard 33-year cycle approximation (accurate for 1178–1633 AP,
// i.e. all dates this product will ever show).

export interface JalaliDate {
  jy: number;
  jm: number;
  jd: number;
}

const G_DAYS_IN_MONTH = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];

function div(a: number, b: number): number {
  return Math.floor(a / b);
}

export function toJalali(date: Date): JalaliDate {
  const gy = date.getFullYear();
  const gm = date.getMonth() + 1;
  const gd = date.getDate();

  let gy2 = gy - 1600;
  const gm2 = gm - 1;
  const gd2 = gd - 1;

  let gDayNo =
    365 * gy2 + div(gy2 + 3, 4) - div(gy2 + 99, 100) + div(gy2 + 399, 400);
  for (let i = 0; i < gm2; i++) gDayNo += G_DAYS_IN_MONTH[i];
  if (gm2 > 1 && ((gy % 4 === 0 && gy % 100 !== 0) || gy % 400 === 0)) {
    gDayNo += 1;
  }
  gDayNo += gd2;

  let jDayNo = gDayNo - 79;
  const jNp = div(jDayNo, 12053);
  jDayNo %= 12053;

  let jy = 979 + 33 * jNp + 4 * div(jDayNo, 1461);
  jDayNo %= 1461;
  if (jDayNo >= 366) {
    jy += div(jDayNo - 1, 365);
    jDayNo = (jDayNo - 1) % 365;
  }

  let jm: number;
  let jd: number;
  if (jDayNo < 186) {
    jm = 1 + div(jDayNo, 31);
    jd = 1 + (jDayNo % 31);
  } else {
    jm = 7 + div(jDayNo - 186, 30);
    jd = 1 + ((jDayNo - 186) % 30);
  }
  void gy2;
  return { jy, jm, jd };
}

export const JALALI_MONTHS = [
  "فروردین",
  "اردیبهشت",
  "خرداد",
  "تیر",
  "مرداد",
  "شهریور",
  "مهر",
  "آبان",
  "آذر",
  "دی",
  "بهمن",
  "اسفند",
];

export const WEEKDAYS_FA = [
  "یکشنبه",
  "دوشنبه",
  "سه‌شنبه",
  "چهارشنبه",
  "پنجشنبه",
  "جمعه",
  "شنبه",
];

/** «سه‌شنبه ۱۷ مرداد ۱۴۰۵» */
export function formatJalali(date: Date, withWeekday = false): string {
  const { jy, jm, jd } = toJalali(date);
  const core = `${jd} ${JALALI_MONTHS[jm - 1]} ${jy}`;
  return withWeekday ? `${WEEKDAYS_FA[date.getDay()]} ${core}` : core;
}

/** «۱۴۰۵/۰۵/۱۷» */
export function formatJalaliShort(date: Date): string {
  const { jy, jm, jd } = toJalali(date);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${jy}/${p(jm)}/${p(jd)}`;
}
