import { useQuery } from "@tanstack/react-query";
import { Activity, ArrowRight, ClipboardCheck, Database, ShieldAlert, Users } from "lucide-react";
import { Link } from "react-router-dom";
import { searchPatients } from "../shared/api/clinicalApi";
import { EmptyState, ErrorState, LoadingState, PartialDataNotice, Section } from "../shared/components/States";
import { PatientTable } from "../features/patients/PatientTable";

export function DashboardPage() {
  const patients = useQuery({ queryKey: ["patients", "dashboard"], queryFn: () => searchPatients({}) });
  return (
    <div className="page-stack">
      <div className="page-heading dashboard-heading">
        <div><span className="eyebrow">Klinischer Überblick</span><h1>Guten Tag</h1><p>Priorisierte Informationen für den aktuellen Pflegekontext.</p></div>
        <Link className="button button-primary" to="/patients">Patienten suchen <ArrowRight aria-hidden="true" /></Link>
      </div>
      <div className="notice notice-info"><ShieldAlert aria-hidden="true" /><span><strong>Entscheidungsunterstützung:</strong> Risikohinweise ersetzen keine klinische Beurteilung.</span></div>
      <div className="metric-grid">
        <article className="metric-card"><span className="metric-icon teal"><Users /></span><div><small>Geladene Patienten</small><strong>{patients.data?.items.length ?? "—"}</strong><span>Aktueller Suchumfang</span></div></article>
        <article className="metric-card"><span className="metric-icon amber"><Activity /></span><div><small>Erhöhtes Risiko</small><strong>—</strong><span>Nicht serverseitig aggregiert</span></div></article>
        <article className="metric-card"><span className="metric-icon blue"><ClipboardCheck /></span><div><small>Offene Warnungen</small><strong>—</strong><span>Keine Warnschnittstelle</span></div></article>
        <article className="metric-card"><span className="metric-icon violet"><Database /></span><div><small>Datenqualität</small><strong>{patients.data ? patients.data.rejectedCount : "—"}</strong><span>Nicht lesbare Datensätze</span></div></article>
      </div>
      <Section title="Patienten im aktuellen Umfang" eyebrow="Übersicht" action={<Link className="text-link" to="/patients">Alle anzeigen <ArrowRight /></Link>}>
        {patients.isPending ? <LoadingState label="Patienten werden geladen" /> : patients.isError ? <ErrorState error={patients.error} onRetry={() => void patients.refetch()} /> : patients.data.items.length === 0 ? <EmptyState title="Keine Patienten gefunden" message="Die aktuelle Suche liefert keine Datensätze." /> : <><PartialDataNotice count={patients.data.rejectedCount} /><PatientTable patients={patients.data.items.slice(0, 5)} /></>}
      </Section>
    </div>
  );
}
