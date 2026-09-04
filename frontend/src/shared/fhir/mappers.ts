import type {
  ClinicalEvent,
  Encounter,
  NursingReport,
  ParsedCollection,
  Patient,
  RiskAssessment,
  VitalKind,
  VitalSign,
} from "../../entities/clinical/model";
import {
  BundleSchema,
  CompositionSchema,
  ClinicalResourceSchema,
  ObservationSchema,
  EncounterSchema,
  PatientSchema,
  RiskAssessmentSchema,
  type FhirClinicalResource,
  type FhirObservation,
  type FhirPatient,
} from "./schemas";

const LOINC_TO_KIND: Record<string, VitalKind> = {
  "8867-4": "heart-rate",
  "85354-9": "blood-pressure",
  "8310-5": "temperature",
  "9279-1": "respiratory-rate",
  "2708-6": "oxygen-saturation",
  "72514-3": "pain",
  "83186-7": "mobility",
  "59460-6": "morse-score",
  "59461-4": "morse-level",
  "59454-9": "fall-history",
};

const KIND_LABEL: Record<VitalKind, string> = {
  "heart-rate": "Herzfrequenz",
  "blood-pressure": "Blutdruck",
  temperature: "Körpertemperatur",
  "respiratory-rate": "Atemfrequenz",
  "oxygen-saturation": "Sauerstoffsättigung",
  pain: "Schmerz",
  mobility: "Mobilität",
  "morse-score": "Morse Fall Scale",
  "morse-level": "Sturzrisikostufe",
  "fall-history": "Sturzanamnese (Morse)",
  other: "Weitere Messung",
};

function firstCoding(concept: {
  coding?: { code?: string | undefined; display?: string | undefined }[] | undefined;
  text?: string | undefined;
}) {
  return concept.coding?.[0];
}

function validDate(value?: string): string | undefined {
  return value && !Number.isNaN(Date.parse(value)) ? value : undefined;
}

export function calculateAge(birthDate?: string, now = new Date()): number | undefined {
  if (!birthDate || !/^\d{4}-\d{2}-\d{2}$/.test(birthDate)) return undefined;
  const birth = new Date(`${birthDate}T00:00:00Z`);
  if (Number.isNaN(birth.getTime()) || birth > now) return undefined;
  let age = now.getUTCFullYear() - birth.getUTCFullYear();
  const beforeBirthday =
    now.getUTCMonth() < birth.getUTCMonth() ||
    (now.getUTCMonth() === birth.getUTCMonth() && now.getUTCDate() < birth.getUTCDate());
  if (beforeBirthday) age -= 1;
  return age;
}

export function mapPatient(input: unknown): Patient {
  const resource: FhirPatient = PatientSchema.parse(input);
  const preferred = resource.name?.find((name) => name.use === "official") ?? resource.name?.[0];
  const composed = [preferred?.given?.join(" "), preferred?.family].filter(Boolean).join(" ");
  const displayName = preferred?.text?.trim() || composed.trim() || "Name nicht verfügbar";
  const birthDate = resource.birthDate && /^\d{4}-\d{2}-\d{2}$/.test(resource.birthDate)
    ? resource.birthDate
    : undefined;
  const age = calculateAge(birthDate);
  const identifier = resource.identifier?.find((item) => item.use === "official")?.value
    ?? resource.identifier?.find((item) => item.value)?.value;
  return {
    id: resource.id,
    displayName,
    gender: mapGender(resource.gender),
    ...(birthDate ? { birthDate } : {}),
    ...(age !== undefined ? { age } : {}),
    ...(identifier ? { identifier } : {}),
  };
}

function mapGender(value?: string): string {
  return ({ female: "Weiblich", male: "Männlich", other: "Divers", unknown: "Unbekannt" } as const)[
    value as "female" | "male" | "other" | "unknown"
  ] ?? "Nicht verfügbar";
}

export function mapObservation(input: unknown): VitalSign {
  const resource: FhirObservation = ObservationSchema.parse(input);
  const coding = firstCoding(resource.code);
  const kind = (coding?.code && LOINC_TO_KIND[coding.code]) || "other";
  const measuredAt = validDate(resource.effectiveDateTime ?? resource.issued);
  const source = resource.performer?.[0]?.display ?? resource.performer?.[0]?.reference
    ?? resource.device?.display ?? resource.device?.reference;
  const base: VitalSign = {
    ...(resource.id ? { id: resource.id } : {}),
    kind,
    label: kind === "other" ? coding?.display || resource.code.text || KIND_LABEL.other : KIND_LABEL[kind],
    ...(resource.status ? { status: resource.status } : {}),
    ...(source ? { source } : {}),
    ...(measuredAt ? { measuredAt } : {}),
  };
  if (kind === "blood-pressure") {
    const systolic = resource.component?.find((item) => firstCoding(item.code)?.code === "8480-6")?.valueQuantity?.value;
    const diastolic = resource.component?.find((item) => firstCoding(item.code)?.code === "8462-4")?.valueQuantity?.value;
    return {
      ...base,
      ...(systolic !== undefined ? { systolic } : {}),
      ...(diastolic !== undefined ? { diastolic } : {}),
      unit: "mmHg",
    };
  }
  const value = resource.valueQuantity?.value;
  const unit = resource.valueQuantity?.unit ?? resource.valueQuantity?.code;
  const textValue = resource.valueCodeableConcept
    ? firstCoding(resource.valueCodeableConcept)?.display ?? resource.valueCodeableConcept.text
    : undefined;
  return {
    ...base,
    ...(value !== undefined ? { value } : {}),
    ...(unit ? { unit } : {}),
    ...(textValue ? { textValue } : {}),
  };
}

export function mapEncounter(input: unknown): Encounter {
  const resource = EncounterSchema.parse(input);
  const identifier = resource.identifier?.find((item) => item.use === "official")?.value
    ?? resource.identifier?.find((item) => item.value)?.value;
  const startedAt = validDate(resource.period?.start);
  return {
    id: resource.id,
    status: resource.status,
    ...(identifier ? { identifier } : {}),
    ...(startedAt ? { startedAt } : {}),
  };
}

function narrativeText(div?: string): string {
  if (!div) return "Inhalt nicht verfügbar";
  const document = new DOMParser().parseFromString(div, "application/xhtml+xml");
  if (document.querySelector("parsererror")) return "Inhalt nicht sicher lesbar";
  return document.documentElement.textContent?.trim() || "Inhalt nicht verfügbar";
}

export function mapNursingReport(input: unknown): NursingReport {
  const resource = CompositionSchema.parse(input);
  const versionId = resource.meta?.versionId;
  if (!versionId) throw new Error("FHIR-Version fehlt");
  const encounterReference = resource.encounter?.reference;
  const encounterId = encounterReference?.match(/^Encounter\/([A-Za-z0-9.-]{1,64})$/)?.[1];
  const authoredAt = validDate(resource.date);
  return {
    id: resource.id,
    versionId,
    status: resource.status,
    title: resource.title,
    text: narrativeText(resource.section?.[0]?.text?.div),
    ...(resource.identifier?.value ? { identifier: resource.identifier.value } : {}),
    ...(authoredAt ? { authoredAt } : {}),
    ...(resource.author?.[0]?.display ? { author: resource.author[0].display } : {}),
    ...(encounterId ? { encounterId } : {}),
  };
}

function conceptText(resource: FhirClinicalResource): string | undefined {
  const concept = resource.code ?? resource.medicationCodeableConcept ?? resource.medication;
  return concept ? firstCoding(concept)?.display ?? concept.text : undefined;
}

export function mapClinicalResource(input: unknown): ClinicalEvent {
  const resource = ClinicalResourceSchema.parse(input);
  const label = conceptText(resource) ?? resource.title ?? resource.summary ?? "Bezeichnung nicht verfügbar";
  const occurredAt = validDate(
    resource.date ?? resource.recordedDate ?? resource.onsetDateTime ?? resource.authoredOn ??
      resource.occurrenceDateTime ?? resource.performedDateTime ?? resource.performedPeriod?.start,
  );
  return {
    ...(resource.id ? { id: resource.id } : {}),
    resourceType: resource.resourceType,
    label,
    ...(resource.status ? { status: resource.status } : {}),
    ...(occurredAt ? { occurredAt } : {}),
    ...(resource.description ? { description: resource.description } : {}),
  };
}

export function mapRiskAssessment(input: unknown): RiskAssessment {
  const resource = RiskAssessmentSchema.parse(input);
  const calculatedAt = validDate(resource.occurrenceDateTime);
  return {
    ...(resource.id ? { id: resource.id } : {}),
    status: resource.status,
    ...(calculatedAt ? { calculatedAt } : {}),
    ...(resource.method
      ? { method: firstCoding(resource.method)?.display ?? resource.method.text ?? "Methode nicht verfügbar" }
      : {}),
    predictions: (resource.prediction ?? []).map((prediction) => ({
      label: firstCoding(prediction.outcome)?.display ?? prediction.outcome.text ?? "Risiko",
      ...(prediction.probabilityDecimal !== undefined
        ? { probability: prediction.probabilityDecimal }
        : {}),
      missingFeatures: (prediction.extension ?? [])
        .filter((extension) => extension.url.endsWith("/missing-features"))
        .flatMap((extension) => extension.valueString?.split(",").map((item) => item.trim()).filter(Boolean) ?? []),
    })),
    ...(resource.note?.[0]?.text ? { note: resource.note[0].text } : {}),
  };
}

export function mapBundle<T>(
  input: unknown,
  mapper: (resource: unknown) => T,
): ParsedCollection<T> {
  const bundle = BundleSchema.parse(input);
  const items: T[] = [];
  let rejectedCount = 0;
  for (const entry of bundle.entry ?? []) {
    try {
      items.push(mapper(entry.resource));
    } catch {
      rejectedCount += 1;
    }
  }
  return { items, rejectedCount };
}
