import type { ParsedCollection, Patient, RiskAssessment, VitalSign, ClinicalEvent } from "../../entities/clinical/model";
import { apiRequest } from "./http";
import {
  BundleSchema,
  ClinicalResourceSchema,
  ObservationSchema,
  PatientSchema,
  RiskAssessmentSchema,
} from "../fhir/schemas";
import { mapBundle, mapClinicalResource, mapObservation, mapPatient, mapRiskAssessment } from "../fhir/mappers";

export type PatientSearchInput = { family?: string; given?: string; birthdate?: string };
export type ClinicalRecordType = "Condition" | "MedicationStatement" | "CarePlan" | "AllergyIntolerance" | "ClinicalImpression";
export type PatientCreateInput = {
  family: string;
  given: string;
  birthDate?: string;
  gender?: "male" | "female" | "other" | "unknown";
};
export type VitalMeasurementType =
  | "heart-rate"
  | "blood-pressure"
  | "temperature"
  | "respiratory-rate"
  | "oxygen-saturation"
  | "pain"
  | "morse-score";
export type VitalMeasurementInput = {
  measurementType: VitalMeasurementType;
  measuredAt: string;
  value?: number;
  systolic?: number;
  diastolic?: number;
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

export async function createPatient(input: PatientCreateInput): Promise<Patient> {
  const resource = await apiRequest("/api/Patient", PatientSchema, {
    method: "POST",
    body: {
      name: [{ family: input.family, given: [input.given] }],
      ...(input.birthDate ? { birthDate: input.birthDate } : {}),
      ...(input.gender ? { gender: input.gender } : {}),
    },
  });
  return mapPatient(resource);
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
  input: { title: string; text: string },
): Promise<ClinicalEvent> {
  const resource = await apiRequest("/api/ui/patient/nursing-reports", ClinicalResourceSchema, {
    method: "POST",
    body: { patientId, ...input },
  });
  return mapClinicalResource(resource);
}
