/** Files the investor drops for A2: media types, base64 reading, sizes, and an example portfolio to paste. */
import type { Locale } from "@/lib/contract/schemas";
import { formatNumber } from "@/lib/i18n/locale";

export const EXAMPLE_PORTFOLIO: Record<Locale, string> = {
  fr: "100 RY.TO CELI\n40 TD.TO CELI\n25 AAPL REER\n15 NVDA REER\n200 XIU.TO non enregistré\n0,05 BTC\nfonds maison XYZ",
  en: "100 RY.TO TFSA\n40 TD.TO TFSA\n25 AAPL RRSP\n15 NVDA RRSP\n200 XIU.TO non-registered\n0.05 BTC\nhouse fund XYZ",
};

const EXTENSION_TYPES: Record<string, string> = {
  csv: "text/csv",
  tsv: "text/tab-separated-values",
  txt: "text/plain",
  md: "text/markdown",
  json: "application/json",
  pdf: "application/pdf",
  xlsx: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  xls: "application/vnd.ms-excel",
  png: "image/png",
  jpg: "image/jpeg",
  jpeg: "image/jpeg",
};

export function mediaTypeOf(file: Pick<File, "name" | "type">): string {
  if (file.type) return file.type;
  const extension = file.name.split(".").pop()?.toLowerCase() ?? "";
  return EXTENSION_TYPES[extension] ?? "application/octet-stream";
}

export function readAsBase64(file: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = String(reader.result ?? "");
      resolve(result.slice(result.indexOf(",") + 1));
    };
    reader.onerror = () => reject(reader.error ?? new Error("read failed"));
    reader.readAsDataURL(file);
  });
}

export function sizeLabel(bytes: number, locale: Locale, units: { bytes: string; kilobytes: string; megabytes: string }): string {
  if (bytes < 1024) return `${bytes} ${units.bytes}`;
  if (bytes < 1024 * 1024) return `${formatNumber(bytes / 1024, locale, 0)} ${units.kilobytes}`;
  return `${formatNumber(bytes / (1024 * 1024), locale, 1)} ${units.megabytes}`;
}
