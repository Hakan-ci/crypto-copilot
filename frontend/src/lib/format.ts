export function formatCurrency(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  const numberValue = Number(value);
  if (!Number.isFinite(numberValue)) {
    return String(value);
  }
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: Math.abs(numberValue) < 1 ? 6 : 2
  }).format(numberValue);
}

export function formatDecimal(value: string | number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  const numberValue = Number(value);
  if (!Number.isFinite(numberValue)) {
    return String(value);
  }
  return new Intl.NumberFormat("en-US", {
    maximumFractionDigits: digits
  }).format(numberValue);
}

export function formatPercent(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  return `${formatDecimal(value, 2)}%`;
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) {
    return "-";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("en-US", {
    dateStyle: "medium",
    timeStyle: "short"
  }).format(date);
}

export function classForPnl(value: string | number | null | undefined): string {
  const numeric = Number(value ?? 0);
  if (numeric > 0) {
    return "text-emerald-700";
  }
  if (numeric < 0) {
    return "text-red-700";
  }
  return "text-slate-700";
}
