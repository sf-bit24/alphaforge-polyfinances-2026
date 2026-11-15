/**
 * A social insurance number (NAS, SIN) in the investor's text, refused like in the real runtime (#77).
 *
 * Same rule as `app/agents/src/alphaforge/personal_data.py`, tested on the same table of cases
 * (`app/agents/tests/fixtures/issue_77_sin_cases.json`). A SIN is:
 * 1. three groups of three digits separated by a space or a dash (the "nas-canadien" regex of the guardrail);
 * 2. 9 joined digits shortly after (20 characters at most, no digit, no line break) a SIN keyword, in French or
 *    English, any case: NAS, N.A.S., (numéro d')assurance sociale, SIN, S.I.N., social insurance (number);
 * 3. 9 joined digits without a keyword, only if they pass the Luhn key and do not look like portfolio data that A2
 *    must read. A numeric CUSIP always passes Luhn, so the context decides: the number is not refused when the text
 *    names a CUSIP, ISIN or SEDOL, or holds several different 9-digit numbers; when it touches an amount (currency,
 *    `%`, decimals); when its neighbour on the line is another number, a ticker or an exchange (AAPL, RY.TO, NASDAQ);
 *    or when an account, quantity or amount word is within 40 characters on the same line.
 */

/** Letters, to bound a word the same way in Python and JavaScript (`\b` differs between the two engines). */
const LETTER = "A-Za-zÀ-ÿ";

const SIN_PATTERN = /\b\d{3}[ -]\d{3}[ -]\d{3}\b/;
const SIN_AFTER_KEYWORD = new RegExp(
  `(?<![${LETTER}])(?:n\\.?a\\.?s|s\\.?i\\.?n|assurance[-\\s]+sociale|social[-\\s]+insurance)\\.?(?![${LETTER}])` +
    "[^0-9\\n]{0,20}(?<![0-9])[0-9]{9}(?![0-9])",
  "i",
);
const BARE_NINE_DIGITS = /(?<![0-9A-Za-z])[0-9]{9}(?![0-9A-Za-z])/g;
const SECURITY_IDS = new RegExp(`(?<![${LETTER}])(?:cusip|isin|sedol)(?![${LETTER}])`, "i");
const HOLDING_WORDS = new RegExp(
  `(?<![${LETTER}])(?:compte|account|acct|folio|quantit[ée]|qt[ée]|qty|quantity|actions?|parts?|unit[ée]s?|units?` +
    `|titres?|shares?|montant|amount|valeur|value|prix|price|total|solde|balance|dollars?|r[ée]f[ée]rence` +
    `|reference|ref)(?![${LETTER}])`,
  "i",
);
const AMOUNT_BEFORE = /(?:[$€£]|\b(?:CAD|USD|EUR)|[0-9][.,])\s?$/i;
const AMOUNT_AFTER = /^(?:\s?(?:[$€£%]|(?:CAD|USD|EUR|dollars?)\b)|[.,][0-9])/i;
/** Separators of a holdings or CSV line, between the number and its neighbours. */
const SEPARATORS = /[\s,;|:/()[\]-]+/;
/** Neighbour of portfolio data: a number, a ticker or an exchange (AAPL, RY.TO, NASDAQ). */
const HOLDING_TOKEN = /[0-9]|^[A-Z]{1,6}(?:\.[A-Z]{1,3})?$/;
const WORD_WINDOW = 40;

/** Luhn key, the one of the SIN: from the right, every second digit is doubled. */
export function luhnValid(digits: string): boolean {
  let total = 0;
  [...digits].reverse().forEach((char, index) => {
    const value = Number(char) * (index % 2 ? 2 : 1);
    total += value > 9 ? value - 9 : value;
  });
  return total % 10 === 0;
}

/** The word before the number on its line and the one after it, without the separators. */
function neighbours(before: string, after: string): string[] {
  const left = before.split(SEPARATORS).filter(Boolean);
  const right = after.split(SEPARATORS).filter(Boolean);
  return [...left.slice(-1), ...right.slice(0, 1)].map((token) => token.replace(/^\.+|\.+$/g, ""));
}

/** The number touches an amount, another number, a ticker, or an account, quantity or amount word of its line. */
function looksLikeHolding(text: string, start: number, end: number): boolean {
  const lineStart = text.lastIndexOf("\n", start - 1) + 1;
  const lineEnd = text.indexOf("\n", end);
  const before = text.slice(lineStart, start);
  const after = text.slice(end, lineEnd >= 0 ? lineEnd : text.length);
  if (AMOUNT_BEFORE.test(before) || AMOUNT_AFTER.test(after)) return true;
  if (neighbours(before, after).some((token) => HOLDING_TOKEN.test(token))) return true;
  return HOLDING_WORDS.test(`${before.slice(-WORD_WINDOW)} ${after.slice(0, WORD_WINDOW)}`);
}

/** Rule 3: 9 joined digits, without a keyword, that pass Luhn outside any portfolio context. */
function bareSin(text: string): boolean {
  const candidates = [...text.matchAll(BARE_NINE_DIGITS)].filter((match) => luhnValid(match[0]));
  const [first] = candidates;
  if (!first || SECURITY_IDS.test(text) || new Set(candidates.map((match) => match[0])).size > 1) return false;
  return !looksLikeHolding(text, first.index, first.index + first[0].length);
}

/** True when the text holds a SIN under the three rules above. */
export function containsSin(text: string): boolean {
  return SIN_PATTERN.test(text) || SIN_AFTER_KEYWORD.test(text) || bareSin(text);
}
