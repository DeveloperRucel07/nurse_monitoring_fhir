import { useQuery } from "@tanstack/react-query";
import { Filter, Plus, Search, Users } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useAuth } from "../features/auth/AuthProvider";
import { PatientAdmissionForm } from "../features/patients/PatientAdmissionForm";
import { PatientTable } from "../features/patients/PatientTable";
import { searchPatients, type PatientSearchInput } from "../shared/api/clinicalApi";
import { EmptyState, ErrorState, LoadingState, PartialDataNotice, Section } from "../shared/components/States";

function cleaned(form: HTMLFormElement): PatientSearchInput {
  const values = new FormData(form);
  const result: PatientSearchInput = {};
  const text = (name: string) => {
    const value = values.get(name);
    return typeof value === "string" ? value.trim() : "";
  };
  const family = text("family");
  const given = text("given");
  const birthdate = text("birthdate");
  if (family) result.family = family;
  if (given) result.given = given;
  if (birthdate) result.birthdate = birthdate;
  return result;
}

export function PatientsPage() {
  const [search, setSearch] = useState<PatientSearchInput>({});
  const [showAdmission, setShowAdmission] = useState(false);
  const { capabilities } = useAuth();
  const patients = useQuery({ queryKey: ["patients", search], queryFn: () => searchPatients(search) });
  const submit = (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); setSearch(cleaned(event.currentTarget)); };
  return (
    <div className="page-stack">
      <div className="page-heading"><div><span className="eyebrow">Patientenmanagement</span><h1>Patientenübersicht</h1><p>FHIR-Stammdaten suchen, sortieren und sicher öffnen.</p></div>{capabilities.canWrite ? <button className="button button-primary" type="button" aria-expanded={showAdmission} onClick={() => setShowAdmission((visible) => !visible)}><Plus />{showAdmission ? "Aufnahme schließen" : "Patient aufnehmen"}</button> : null}</div>
      {showAdmission && capabilities.canWrite ? <Section title="Neue Patientenaufnahme" eyebrow="Schreibberechtigung erforderlich"><PatientAdmissionForm onCancel={() => setShowAdmission(false)} /></Section> : null}
      {!capabilities.canWrite ? <div className="notice notice-info"><Users aria-hidden="true" /><span>Sie besitzen Leserechte. Für eine Patientenaufnahme ist die Rolle „pflege_write“ erforderlich.</span></div> : null}
      <Section title="Patientensuche" eyebrow="Datensparsam" className="search-panel">
        <form className="search-form" onSubmit={submit}>
          <label><span>Nachname</span><input name="family" maxLength={100} autoComplete="off" /></label>
          <label><span>Vorname</span><input name="given" maxLength={100} autoComplete="off" /></label>
          <label><span>Geburtsdatum</span><input name="birthdate" type="date" /></label>
          <button className="button button-primary" type="submit"><Search />Suchen</button>
        </form>
        <p className="form-help"><Filter aria-hidden="true" /> Suchdaten werden nicht in der URL oder im Browser gespeichert.</p>
      </Section>
      <Section title="Suchergebnis" eyebrow={patients.data ? `${patients.data.items.length} Datensätze` : "FHIR"}>
        {patients.isPending ? <LoadingState label="Patienten werden geladen" /> : patients.isError ? <ErrorState error={patients.error} onRetry={() => void patients.refetch()} /> : patients.data.items.length === 0 ? <EmptyState title="Keine passenden Patienten" message="Passen Sie die Suchkriterien an oder prüfen Sie den Datenbestand." /> : <><PartialDataNotice count={patients.data.rejectedCount} /><PatientTable patients={patients.data.items} /></>}
      </Section>
      <div className="data-note"><Users aria-hidden="true" /><span>Station, Zimmer, letzter Messzeitpunkt und Warnstatus werden derzeit nicht durch eine geeignete Backend-Schnittstelle bereitgestellt.</span></div>
    </div>
  );
}
