"""Jalali (Shamsi) calendar conversion — pure Python, no deps (D5)."""
from __future__ import annotations

from datetime import date

MONTHS_FA = [
    "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
    "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند",
]

_PERSIAN_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def gregorian_to_jalali(gy: int, gm: int, gd: int) -> tuple[int, int, int]:
    """Standard arithmetic conversion (Behrooz–Birashk algorithm)."""
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    gy2 = gy + 1 if gm > 2 else gy
    days = (
        355666 + (365 * gy) + ((gy2 + 3) // 4) - ((gy2 + 99) // 100)
        + ((gy2 + 399) // 400) + gd + g_d_m[gm - 1]
    )
    jy = -1595 + (33 * (days // 12053))
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jm = 1 + (days // 31)
        jd = 1 + (days % 31)
    else:
        jm = 7 + ((days - 186) // 30)
        jd = 1 + ((days - 186) % 30)
    return jy, jm, jd


def jalali_str(d: date, *, persian_digits: bool = True, with_month_name: bool = True) -> str:
    jy, jm, jd = gregorian_to_jalali(d.year, d.month, d.day)
    if with_month_name:
        s = f"{jd} {MONTHS_FA[jm - 1]} {jy}"
    else:
        s = f"{jy}/{jm:02d}/{jd:02d}"
    return s.translate(_PERSIAN_DIGITS) if persian_digits else s
