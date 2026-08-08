// Persian digit rendering (D5). Applied at display time only —
// data stays in ASCII digits.

const FA_DIGITS = "۰۱۲۳۴۵۶۷۸۹";

export function toPersianDigits(input: string | number): string {
  return String(input).replace(/[0-9]/g, (d) => FA_DIGITS[Number(d)]);
}

/** Respects the user's "Persian digits" setting. */
export function digits(input: string | number, persian: boolean): string {
  return persian ? toPersianDigits(input) : String(input);
}
