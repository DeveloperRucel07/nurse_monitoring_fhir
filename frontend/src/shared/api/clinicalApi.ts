import type { ClinicalEvent, Encounter, NursingReport, ParsedCollection, Patient, RiskAssessment, VitalSign } from "../../entities/clinical/model";
import { apiRequest } from "./http";
import {
  BundleSchema,
  AdmissionResponseSchema,
  CompositionSchema,
  ObservationSchema,
  PatientSchema,
  RiskAssessmentSchema,
} from "../fhir/schemas";
import { mapBundle, mapClinicalResource, mapEncounter, mapNursingReport, mapObservation, mapPatient, mapRiskAssessment } from "../fhir/mappers";

export type PatientSearchInput = { family?: string; given?: string; birthdate?: string };
export type ClinicalRecordType = "Condition" | "MedicationStatement" | "CarePlan" | "AllergyIntolerance" | "ClinicalImpression";
export type PatientCreateInput = {
  family: string;
  given: string;
  birthDate?: string;
  gender?: "male" | "female" | "other" | "unknown";
  admittedAt: string;
};
export type VitalMeasurementType =
  | "heart-rate"
  | "blood-pressure"
  | "temperature"
  | "respiratory-rate"
  | "oxygen-saturation"
  | "pain"
  | "morse-score"
  | "mobility"
  | "fall-history";
export type VitalMeasurementInput = {
  measurementType: VitalMeasurementType;
  encounterId: string;
  measuredAt: string;
  value?: number;
  systolic?: number;
  diastolic?: number;
  codedValue?: "independent" | "needs-help" | "dependent" | "yes" | "no";
};

export async function searchPatients(input: PatientSearchInput): Promise<ParsedCollection<Patient>> {
  const bundle = await apiRequest("/api/ui/patients/search", BundleSchema, { method: "POST", body: input });
  return mapBundle(bundle, mapPatient);
}

export async function getPatient(patientId: string): Promise<Patient> {
  const resource = await apiRequest("/api/ui/patient/read", PatientSchema, { method: "POST", body: { patientId } });
  return mapPatient(resource);
}

export async function getObservations(patientId: string): Promise<ParsedCollection<VitalSign>> {
  const bundle = await apiRequest("/api/ui/patient/observations", BundleSchema, {
    method: "POST",
    body: { patientId },
  });
  return mapBundle(bundle, mapObservation);
}

export async function getClinicalRecords(
  patientId: string,
  recordType: ClinicalRecordType,
): Promise<ParsedCollection<ClinicalEvent>> {
  const bundle = await apiRequest("/api/ui/patient/clinical-records", BundleSchema, {
    method: "POST",
    body: { patientId, recordType },
  });
  return mapBundle(bundle, mapClinicalResource);
}

export async function getRiskAssessment(patientId: string): Promise<RiskAssessment> {
  const resource = await apiRequest("/api/ui/patient/risk-assessment", RiskAssessmentSchema, {
    method: "POST",
    body: { patientId },
  });
  return mapRiskAssessment(resource);
}

export async function admitPatient(input: PatientCreateInput): Promise<{ patient: Patient; encounter: Encounter }> {
  const resource = await apiRequest("/api/ui/patients/admit", AdmissionResponseSchema, {
    method: "POST",
    body: {
      name: [{ family: input.family, given: [input.given] }],
      ...(input.birthDate ? { birthDate: input.birthDate } : {}),
      ...(input.gender ? { gender: input.gender } : {}),
      admittedAt: input.admittedAt,
    },
  });
  return { patient: mapPatient(resource.patient), encounter: mapEncounter(resource.encounter) };
}

export async function createVitalMeasurement(
  patientId: string,
  input: VitalMeasurementInput,
): Promise<VitalSign> {
  const resource = await apiRequest("/api/ui/patient/vital-measurements", ObservationSchema, {
    method: "POST",
    body: { patientId, ...input },
  });
  return mapObservation(resource);
}

export async function createNursingReport(
  patientId: string,
  input: { encounterId: string; title: string; text: string },
): Promise<NursingReport> {
  const resource = await apiRequest("/api/ui/patient/nursing-reports", CompositionSchema, {
    method: "POST",
    body: { patientId, ...input },
  });
  return mapNursingReport(resource);
}

export async function getEncounters(patientId: string): Promise<ParsedCollection<Encounter>> {
  const bundle = await apiRequest("/api/ui/patient/encounters", BundleSchema, { method: "POST", body: { patientId } });
  return mapBundle(bundle, mapEncounter);
}

export async function getNursingReports(patientId: string): Promise<ParsedCollection<NursingReport>> {
  const bundle = await apiRequest("/api/ui/patient/nursing-reports/search", BundleSchema, { method: "POST", body: { patientId } });
  return mapBundle(bundle, mapNursingReport);
}

export async function correctNursingReport(patientId: string, report: NursingReport, title: string, text: string): Promise<NursingReport> {
  const resource = await apiRequest("/api/ui/patient/nursing-reports", CompositionSchema, {
    method: "PUT",
    body: { patientId, reportId: report.id, expectedVersionId: report.versionId, title, text },
  });
  return mapNursingReport(resource);
}

export async function markNursingReportEnteredInError(patientId: string, report: NursingReport, reason: string): Promise<NursingReport> {
  const resource = await apiRequest("/api/ui/patient/nursing-reports/entered-in-error", CompositionSchema, {
    method: "POST",
    body: { patientId, reportId: report.id, expectedVersionId: report.versionId, reason },
  });
  return mapNursingReport(resource);
}
