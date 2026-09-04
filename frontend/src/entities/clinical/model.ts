export type Patient = {
  id: string;
  displayName: string;
  birthDate?: string;
  age?: number;
  gender: string;
  identifier?: string;
};

export type VitalKind =
  | "heart-rate"
  | "blood-pressure"
  | "temperature"
  | "respiratory-rate"
  | "oxygen-saturation"
  | "pain"
  | "mobility"
  | "morse-score"
  | "morse-level"
  | "other";

export type VitalSign = {
  id?: string;
  kind: VitalKind;
  label: string;
  measuredAt?: string;
  status?: string;
  source?: string;
  value?: number;
  unit?: string;
  systolic?: number;
  diastolic?: number;
  textValue?: string;
};

export type ClinicalEvent = {
  id?: string;
  resourceType: string;
  label: string;
  status?: string;
  occurredAt?: string;
  description?: string;
};

export type RiskPrediction = {
  label: string;
  probability?: number;
  missingFeatures: string[];
};

export type RiskAssessment = {
  id?: string;
  status: string;
  calculatedAt?: string;
  method?: string;
  predictions: RiskPrediction[];
  note?: string;
};

export type ParsedCollection<T> = {
  items: T[];
  rejectedCount: number;
};
