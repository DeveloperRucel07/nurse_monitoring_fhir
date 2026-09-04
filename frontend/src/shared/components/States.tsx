import { AlertTriangle, Inbox, LoaderCircle, ShieldAlert, WifiOff } from "lucide-react";
import type { ReactNode } from "react";
import { ApiError } from "../api/http";

export function FullPageState({ title, message, loading = false }: { title: string; message: string; loading?: boolean }) {
  return (
    <main className="centered-page" aria-busy={loading}>
      <div className="state-card">
        {loading ? <LoaderCircle className="spin" aria-hidden="true" /> : <ShieldAlert aria-hidden="true" />}
        <h1>{title}</h1>
        <p>{message}</p>
      </div>
    </main>
  );
}

export function LoadingState({ label = "Daten werden geladen" }: { label?: string }) {
  return (
    <div className="inline-state" role="status" aria-live="polite">
      <LoaderCircle className="spin" aria-hidden="true" />
      <span>{label}</span>
    </div>
  );
}

export function EmptyState({ title, message }: { title: string; message: string }) {
  return (
    <div className="empty-state">
      <Inbox aria-hidden="true" />
      <strong>{title}</strong>
      <span>{message}</span>
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const offline = error instanceof ApiError && error.kind === "network";
  const forbidden = error instanceof ApiError && error.kind === "forbidden";
  const message = error instanceof ApiError ? error.message : "Die Daten konnten nicht geladen werden.";
  return (
    <div className="error-state" role="alert">
      {offline ? <WifiOff aria-hidden="true" /> : <AlertTriangle aria-hidden="true" />}
      <div>
        <strong>{forbidden ? "Keine Berechtigung" : offline ? "Keine Verbindung" : "Daten nicht verfügbar"}</strong>
        <p>{message}</p>
        {onRetry ? <button className="button button-secondary" onClick={onRetry}>Erneut versuchen</button> : null}
      </div>
    </div>
  );
}

export function PartialDataNotice({ count }: { count: number }) {
  if (count === 0) return null;
  return (
    <div className="notice notice-warning" role="status">
      <AlertTriangle aria-hidden="true" />
      <span>{count} Datensätze konnten wegen unvollständiger oder ungültiger FHIR-Daten nicht sicher dargestellt werden.</span>
    </div>
  );
}

export function Section({ title, eyebrow, action, children, className = "" }: {
  title: string;
  eyebrow?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`panel ${className}`}>
      <div className="section-heading">
        <div>{eyebrow ? <span className="eyebrow">{eyebrow}</span> : null}<h2>{title}</h2></div>
        {action}
      </div>
      {children}
    </section>
  );
}
