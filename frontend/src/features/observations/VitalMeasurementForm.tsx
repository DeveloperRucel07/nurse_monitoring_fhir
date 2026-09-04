import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Activity, CheckCircle2 } from "lucide-react";
import { useState, type FormEvent } from "react";
import { createVitalMeasurement, type VitalMeasurementInput, type VitalMeasurementType } from "../../shared/api/clinicalApi";
import { ApiError } from "../../shared/api/http";

const definitions: Record<Exclude<VitalMeasurementType, "blood-pressure" | "mobility" | "fall-history">, { label: string; unit: string; min: number; max: number; step: number }> = {
  "heart-rate": { label: "Herzfrequenz", unit: "/min", min: 1, max: 400, step: 1 },
  temperature: { label: "Körpertemperatur", unit: "°C", min: 20, max: 50, step: 0.1 },
  "respiratory-rate": { label: "Atemfrequenz", unit: "/min", min: 1, max: 150, step: 1 },
  "oxygen-saturation": { label: "Sauerstoffsättigung", unit: "%", min: 0, max: 100, step: 0.1 },
  pain: { label: "Schmerzscore", unit: "0–10", min: 0, max: 10, step: 1 },
  "morse-score": { label: "Morse Fall Scale", unit: "0–125", min: 0, max: 125, step: 1 },
};

function localDateTimeNow(): string {
  const now = new Date();
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 16);
}

function numeric(values: FormData, name: string): number {
  const raw = values.get(name);
  return Number(typeof raw === "string" ? raw : Number.NaN);
}

function selected(values: FormData, name: string): string {
  const raw = values.get(name);
  return typeof raw === "string" ? raw : "";
}

export function VitalMeasurementForm({ patientId, encounterId }: { patientId: string; encounterId: string }) {
  const [measurementType, setMeasurementType] = useState<VitalMeasurementType>("heart-rate");
  const [success, setSuccess] = useState(false);
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: (input: VitalMeasurementInput) => createVitalMeasurement(patientId, input),
    onSuccess: async () => {
      setSuccess(true);
      await queryClient.invalidateQueries({ queryKey: ["observations", patientId] });
    },
  });

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSuccess(false);
    const values = new FormData(event.currentTarget);
    const measuredAt = values.get("measuredAt");
    if (typeof measuredAt !== "string" || !measuredAt) return;
    const input: VitalMeasurementInput = {
      measurementType,
      encounterId,
      measuredAt: new Date(measuredAt).toISOString(),
      ...(measurementType === "blood-pressure"
        ? { systolic: numeric(values, "systolic"), diastolic: numeric(values, "diastolic") }
        : measurementType === "mobility" || measurementType === "fall-history"
          ? { codedValue: selected(values, "codedValue") as NonNullable<VitalMeasurementInput["codedValue"]> }
          : { value: numeric(values, "value") }),
    };
    mutation.mutate(input);
  };

  const isCoded = measurementType === "mobility" || measurementType === "fall-history";
  const definition = measurementType === "blood-pressure" || isCoded ? undefined : definitions[measurementType];
  const errorMessage = mutation.error instanceof ApiError
    ? mutation.error.message
    : "Der Messwert konnte nicht gespeichert werden.";

  return (
    <form className="clinical-form" onSubmit={submit}>
      <div className="form-intro"><Activity aria-hidden="true" /><div><strong>Messung oder Assessment dokumentieren</strong><p>Wert, Fallbezug und Zeitpunkt vor dem Speichern kontrollieren.</p></div></div>
      <div className="form-grid two-columns">
        <label><span>Parameter *</span><select value={measurementType} onChange={(event) => { setMeasurementType(event.target.value as VitalMeasurementType); setSuccess(false); }}><option value="heart-rate">Herzfrequenz</option><option value="blood-pressure">Blutdruck</option><option value="temperature">Körpertemperatur</option><option value="respiratory-rate">Atemfrequenz</option><option value="oxygen-saturation">Sauerstoffsättigung</option><option value="pain">Schmerzscore</option><option value="morse-score">Morse Fall Scale</option><option value="mobility">Mobilität</option><option value="fall-history">Sturzanamnese (Morse)</option></select></label>
        <label><span>Messzeitpunkt *</span><input name="measuredAt" type="datetime-local" required defaultValue={localDateTimeNow()} /></label>
        {measurementType === "blood-pressure" ? <>
          <label><span>Systolisch (mmHg) *</span><input name="systolic" type="number" required min={20} max={350} step={1} inputMode="decimal" /></label>
          <label><span>Diastolisch (mmHg) *</span><input name="diastolic" type="number" required min={20} max={350} step={1} inputMode="decimal" /></label>
        </> : isCoded ? <label><span>Einschätzung *</span><select name="codedValue" required defaultValue=""> <option value="" disabled>Bitte auswählen</option>{measurementType === "mobility" ? <><option value="independent">Selbstständig</option><option value="needs-help">Benötigt Unterstützung</option><option value="dependent">Abhängig</option></> : <><option value="no">Kein Sturz unmittelbar oder innerhalb von 3 Monaten</option><option value="yes">Sturz unmittelbar oder innerhalb von 3 Monaten</option></>}</select></label> : <label><span>{definition?.label} ({definition?.unit}) *</span><input name="value" type="number" required min={definition?.min} max={definition?.max} step={definition?.step} inputMode="decimal" /></label>}
      </div>
      <p className="form-help">Die Grenzen verhindern Eingabefehler; sie stellen keine klinische Bewertung dar.</p>
      {mutation.isError ? <p className="form-error" role="alert">{errorMessage}</p> : null}
      {success ? <p className="form-success" role="status"><CheckCircle2 />Messwert wurde als finale FHIR Observation gespeichert.</p> : null}
      <div className="form-actions"><button className="button button-primary" type="submit" disabled={mutation.isPending}>{mutation.isPending ? "Wird gespeichert …" : "Messwert dokumentieren"}</button></div>
    </form>
  );
}
