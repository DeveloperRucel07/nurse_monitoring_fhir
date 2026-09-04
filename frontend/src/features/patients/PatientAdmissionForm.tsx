import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, UserRoundPlus } from "lucide-react";
import { useRef, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { createPatient, type PatientCreateInput } from "../../shared/api/clinicalApi";
import { ApiError } from "../../shared/api/http";
import { usePatientContext } from "./PatientContext";

function field(form: FormData, name: string): string {
  const value = form.get(name);
  return typeof value === "string" ? value.trim() : "";
}

export function PatientAdmissionForm({ onCancel }: { onCancel: () => void }) {
  const formRef = useRef<HTMLFormElement>(null);
  const [success, setSuccess] = useState(false);
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { selectPatient } = usePatientContext();
  const mutation = useMutation({
    mutationFn: createPatient,
    onSuccess: async (patient) => {
      setSuccess(true);
      selectPatient(patient.id);
      await queryClient.invalidateQueries({ queryKey: ["patients"] });
      void navigate("/patient");
    },
  });

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSuccess(false);
    const values = new FormData(event.currentTarget);
    const gender = field(values, "gender");
    const input: PatientCreateInput = {
      family: field(values, "family"),
      given: field(values, "given"),
      ...(field(values, "birthDate") ? { birthDate: field(values, "birthDate") } : {}),
      ...(gender ? { gender: gender as NonNullable<PatientCreateInput["gender"]> } : {}),
    };
    mutation.mutate(input);
  };

  const message = mutation.error instanceof ApiError
    ? mutation.error.message
    : "Die Patientenaufnahme konnte nicht gespeichert werden.";

  return (
    <form ref={formRef} className="clinical-form" onSubmit={submit}>
      <div className="form-intro">
        <UserRoundPlus aria-hidden="true" />
        <div>
          <strong>FHIR-Patientenakte anlegen</strong>
          <p>Vor dem Speichern Identität und mögliche Dubletten im Bestand prüfen.</p>
        </div>
      </div>
      <div className="form-grid two-columns">
        <label><span>Nachname *</span><input name="family" required minLength={1} maxLength={100} autoComplete="off" /></label>
        <label><span>Vorname *</span><input name="given" required minLength={1} maxLength={100} autoComplete="off" /></label>
        <label><span>Geburtsdatum</span><input name="birthDate" type="date" max={new Date().toISOString().slice(0, 10)} /></label>
        <label><span>Geschlecht</span><select name="gender" defaultValue=""><option value="">Nicht angegeben</option><option value="female">Weiblich</option><option value="male">Männlich</option><option value="other">Divers</option><option value="unknown">Unbekannt</option></select></label>
      </div>
      <label className="confirmation-row">
        <input name="identityConfirmed" type="checkbox" required />
        <span>Identität wurde geprüft und eine Dublettensuche wurde durchgeführt.</span>
      </label>
      <div className="notice notice-warning"><AlertTriangle aria-hidden="true" /><span>Aktuell wird nur eine FHIR-ID erzeugt. Eine klinische Patienten-/Fallnummer kann noch nicht sicher erfasst werden.</span></div>
      {mutation.isError ? <p className="form-error" role="alert">{message}</p> : null}
      {success ? <p className="form-success" role="status"><CheckCircle2 />Patientenakte wurde angelegt.</p> : null}
      <div className="form-actions">
        <button className="button button-secondary" type="button" onClick={onCancel} disabled={mutation.isPending}>Abbrechen</button>
        <button className="button button-primary" type="submit" disabled={mutation.isPending}>{mutation.isPending ? "Wird aufgenommen …" : "Patient aufnehmen"}</button>
      </div>
    </form>
  );
}
