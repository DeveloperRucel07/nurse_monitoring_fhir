export function formatDate(value?: string): string {
  if (!value || Number.isNaN(Date.parse(value))) return "Nicht verfügbar";
  return new Intl.DateTimeFormat("de-DE", { dateStyle: "medium" }).format(new Date(value));
}

export function formatDateTime(value?: string): string {
  if (!value || Number.isNaN(Date.parse(value))) return "Zeitpunkt nicht verfügbar";
  return new Intl.DateTimeFormat("de-DE", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

export function formatTime(value?: string): string {
  if (!value || Number.isNaN(Date.parse(value))) return "—";
  return new Intl.DateTimeFormat("de-DE", { hour: "2-digit", minute: "2-digit" }).format(new Date(value));
}

export function maskIdentifier(value: string): string {
  if (value.length <= 4) return "••••";
  return `${"•".repeat(Math.min(8, value.length - 4))}${value.slice(-4)}`;
}
