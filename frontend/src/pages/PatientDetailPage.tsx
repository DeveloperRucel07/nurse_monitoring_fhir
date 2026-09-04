import { useQueries, useQuery } from "@tanstack/react-query";
import { ArrowLeft, CalendarDays, CircleUserRound, IdCard, MapPin, ShieldCheck } from "lucide-react";
import { Link } from "react-router-dom";
import { ClinicalTimeline } from "../features/clinical/ClinicalTimeline";
import { NursingReportForm } from "../features/clinical/NursingReportForm";
import { useAuth } from "../features/auth/AuthProvider";
import { usePatientContext } from "../features/patients/PatientContext";
import { RiskPanel } from "../features/risk-assessment/RiskPanel";
import { TrendChart } from "../features/observations/TrendChart";
import { VitalMeasurementForm } from "../features/observations/VitalMeasurementForm";
import { VitalGrid } from "../features/observations/VitalGrid";
import { getClinicalRecords, getObservations, getPatient, getRiskAssessment, type ClinicalRecordType } from "../shared/api/clinicalApi";
import { EmptyState, ErrorState, LoadingState, PartialDataNotice, Section } from "../shared/components/States";
import { formatDate, maskIdentifier } from "../shared/utils/format";

const recordTypes = ["Condition", "MedicationStatement", "CarePlan", "AllergyIntolerance", "ClinicalImpression"] as const satisfies readonly ClinicalRecordType[];
const resourceLabels: Record<string, string> = {
  Condition: "Diagnosen / Probleme",
  MedicationStatement: "Medikationsangaben",
  CarePlan: "Versorgungspläne",
  AllergyIntolerance: "Allergien / Unverträglichkeiten",
  ClinicalImpression: "Klinische Einschätzungen",
};

export function PatientDetailPage() {
  const { selectedPatientId, privacyMask } = usePatientContext();
  const { capabilities, features } = useAuth();
  const patient = useQuery({ queryKey: ["patient", selectedPatientId], queryFn: () => getPatient(selectedPatientId ?? ""), enabled: Boolean(selectedPatientId) });
  const observations = useQuery({ queryKey: ["observations", selectedPatientId], queryFn: () => getObservations(selectedPatientId ?? ""), enabled: Boolean(selectedPatientId) });
  const recordResults = useQueries({ queries: recordTypes.map((recordType) => ({ queryKey: ["clinical-records", selectedPatientId, recordType], queryFn: () => getClinicalRecords(selectedPatientId ?? "", recordType), enabled: Boolean(selectedPatientId) })) });
  const risk = useQuery({ queryKey: ["risk", selectedPatientId], queryFn: () => getRiskAssessment(selectedPatientId ?? ""), enabled: Boolean(selectedPatientId) && features.experimentalMl, retry: false });

  if (!selectedPatientId) return <div className="page-stack"><div className="page-heading"><div><span className="eyebrow">Geschützter Kontext</span><h1>Keine Patientenakte ausgewählt</h1><p>Patienten-IDs werden aus Datenschutzgründen nicht in der URL gespeichert.</p></div></div><EmptyState title="Patient auswählen" message="Öffnen Sie die Patientenübersicht und wählen Sie dort eine Akte aus." /><Link className="button button-primary self-start" to="/patients"><ArrowLeft />Zur Patientenübersicht</Link></div>;
  if (patient.isPending) return <LoadingState label="Patientenakte wird geladen" />;
  if (patient.isError) return <ErrorState error={patient.error} onRetry={() => void patient.refetch()} />;

  const allEvents = recordResults.flatMap((result) => result.data?.items ?? []);
  const rejected = (observations.data?.rejectedCount ?? 0) + recordResults.reduce((sum, result) => sum + (result.data?.rejectedCount ?? 0), 0);
  const id = patient.data.identifier ?? patient.data.id;
  return <div className="page-stack">
    <Link className="back-link" to="/patients"><ArrowLeft />Patientenübersicht</Link>
    <section className="patient-header">
      <div className="patient-identity"><span className="large-avatar"><CircleUserRound /></span><div><span className="eyebrow">Aktive Patientenakte</span><h1>{privacyMask ? "Name geschützt" : patient.data.displayName}</h1><div className="patient-meta"><span><IdCard />ID: {privacyMask ? maskIdentifier(id) : id}</span><span><CalendarDays />{privacyMask ? "Geburtsdatum geschützt" : `${formatDate(patient.data.birthDate)}${patient.data.age !== undefined ? ` · ${patient.data.age} Jahre` : ""}`}</span><span><MapPin />Station / Zimmer nicht verfügbar</span></div></div></div>
      <span className="status-badge success"><ShieldCheck />FHIR-Akte geladen</span>
    </section>
    <PartialDataNotice count={rejected} />
    {capabilities.canWrite ? <Section title="Pflegedokumentation" eyebrow="Sicher erfassen">
      <div className="content-grid clinical-actions-grid">
        <VitalMeasurementForm patientId={selectedPatientId} />
        <NursingReportForm patientId={selectedPatientId} />
      </div>
    </Section> : <div className="notice notice-info"><ShieldCheck aria-hidden="true" /><span>Diese Akte ist schreibgeschützt. Für Messwerte und Pflegeberichte ist die Rolle „pflege_write“ erforderlich.</span></div>}
    <Section title="Aktueller Status" eyebrow="Letzte verfügbare Messwerte">
      {observations.isPending ? <LoadingState label="Messwerte werden geladen" /> : observations.isError ? <ErrorState error={observations.error} onRetry={() => void observations.refetch()} /> : <VitalGrid observations={observations.data.items} />}
    </Section>
    <div className="content-grid two-thirds">
      <Section title="Verlauf" eyebrow="Bis zu 30 Messzeitpunkte">
        {observations.data ? <TrendChart observations={observations.data.items} /> : <LoadingState />}
      </Section>
      <Section title="Datenquellen" eyebrow="FHIR-Ressourcen">
        <ul className="resource-status-list">
          {recordTypes.map((type, index) => <li key={type}><span><i className={recordResults[index]?.isError ? "dot error" : "dot"} />{resourceLabels[type]}</span><strong>{recordResults[index]?.isPending ? "Lädt …" : recordResults[index]?.isError ? "Fehler" : `${recordResults[index]?.data?.items.length ?? 0}`}</strong></li>)}
          <li><span><i className="dot neutral" />MedicationRequest</span><strong>Nicht angebunden</strong></li>
          <li><span><i className="dot neutral" />Procedure</span><strong>Nicht angebunden</strong></li>
        </ul>
        <p className="section-note">„0“ bedeutet keine im Suchergebnis gelieferten Einträge. „Nicht angebunden“ ist keine klinische Aussage.</p>
      </Section>
    </div>
    <Section title="Clinical Timeline" eyebrow="Chronologisch">
      {observations.isPending || recordResults.some((result) => result.isPending) ? <LoadingState label="Klinische Ereignisse werden zusammengeführt" /> : <ClinicalTimeline observations={observations.data?.items ?? []} events={allEvents} />}
    </Section>
    <Section title="Risikobewertung" eyebrow="Entscheidungsunterstützung">
      {!features.experimentalMl ? <div className="disabled-feature"><ShieldCheck /><div><strong>ML-Risikobewertung ist sicher deaktiviert</strong><p>Es wird keine automatisierte Risikoeinschätzung erzeugt. Klinische Risiken müssen anhand validierter Verfahren beurteilt werden.</p></div></div> : risk.isPending ? <LoadingState label="Experimentelle Bewertung wird geladen" /> : risk.isError ? <ErrorState error={risk.error} onRetry={() => void risk.refetch()} /> : <RiskPanel assessment={risk.data} />}
    </Section>
  </div>;
}
