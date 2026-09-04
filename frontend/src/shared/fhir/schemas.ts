import { z } from "zod";

const CodingSchema = z.looseObject({
  system: z.string().optional(),
  code: z.string().optional(),
  display: z.string().optional(),
});

const CodeableConceptSchema = z.looseObject({
  coding: z.array(CodingSchema).optional(),
  text: z.string().optional(),
});

const QuantitySchema = z.looseObject({
  value: z.number().finite().optional(),
  unit: z.string().optional(),
  code: z.string().optional(),
});

export const PatientSchema = z.looseObject({
  resourceType: z.literal("Patient"),
  id: z.string().min(1).max(64),
  identifier: z
    .array(z.looseObject({ system: z.string().optional(), value: z.string().optional(), use: z.string().optional() }))
    .optional(),
  name: z
    .array(
      z.looseObject({
        use: z.string().optional(),
        family: z.string().optional(),
        given: z.array(z.string()).optional(),
        text: z.string().optional(),
      }),
    )
    .optional(),
  gender: z.string().optional(),
  birthDate: z.string().optional(),
});

export const ObservationSchema = z.looseObject({
  resourceType: z.literal("Observation"),
  id: z.string().optional(),
  status: z.string().optional(),
  code: CodeableConceptSchema,
  effectiveDateTime: z.string().optional(),
  issued: z.string().optional(),
  performer: z
    .array(z.looseObject({ display: z.string().optional(), reference: z.string().optional() }))
    .optional(),
  device: z.looseObject({ display: z.string().optional(), reference: z.string().optional() }).optional(),
  valueQuantity: QuantitySchema.optional(),
  valueCodeableConcept: CodeableConceptSchema.optional(),
  component: z
    .array(
      z.looseObject({
        code: CodeableConceptSchema,
        valueQuantity: QuantitySchema.optional(),
      }),
    )
    .optional(),
});

const ReferenceSchema = z.looseObject({
  reference: z.string().optional(),
  display: z.string().optional(),
  identifier: z.looseObject({ system: z.string().optional(), value: z.string().optional() }).optional(),
});

export const EncounterSchema = z.looseObject({
  resourceType: z.literal("Encounter"),
  id: z.string().min(1).max(64),
  identifier: z.array(z.looseObject({ system: z.string().optional(), value: z.string().optional(), use: z.string().optional() })).optional(),
  status: z.string(),
  subject: ReferenceSchema.optional(),
  period: z.looseObject({ start: z.string().optional(), end: z.string().optional() }).optional(),
});

export const CompositionSchema = z.looseObject({
  resourceType: z.literal("Composition"),
  id: z.string().min(1).max(64),
  meta: z.looseObject({ versionId: z.string().min(1).max(64).optional() }).optional(),
  identifier: z.looseObject({ system: z.string().optional(), value: z.string().optional() }).optional(),
  status: z.enum(["preliminary", "final", "amended", "entered-in-error"]),
  title: z.string().max(200),
  date: z.string().optional(),
  author: z.array(ReferenceSchema).optional(),
  encounter: ReferenceSchema.optional(),
  section: z.array(z.looseObject({
    text: z.looseObject({ status: z.string().optional(), div: z.string().max(10000).optional() }).optional(),
  })).optional(),
});

export const AdmissionResponseSchema = z.object({
  patient: PatientSchema,
  encounter: EncounterSchema,
});

export const ClinicalResourceSchema = z.looseObject({
  resourceType: z.enum([
    "Condition",
    "MedicationStatement",
    "MedicationRequest",
    "Procedure",
    "CarePlan",
    "AllergyIntolerance",
    "ClinicalImpression",
  ]),
  id: z.string().optional(),
  status: z.string().optional(),
  clinicalStatus: CodeableConceptSchema.optional(),
  code: CodeableConceptSchema.optional(),
  medicationCodeableConcept: CodeableConceptSchema.optional(),
  medication: CodeableConceptSchema.optional(),
  title: z.string().optional(),
  description: z.string().optional(),
  summary: z.string().optional(),
  date: z.string().optional(),
  recordedDate: z.string().optional(),
  onsetDateTime: z.string().optional(),
  authoredOn: z.string().optional(),
  occurrenceDateTime: z.string().optional(),
  performedDateTime: z.string().optional(),
  performedPeriod: z
    .looseObject({ start: z.string().optional(), end: z.string().optional() })
    .optional(),
});

const RiskExtensionSchema = z.looseObject({
  url: z.string(),
  valueCode: z.string().optional(),
  valueString: z.string().optional(),
});

export const RiskAssessmentSchema = z.looseObject({
  resourceType: z.literal("RiskAssessment"),
  id: z.string().optional(),
  status: z.string(),
  occurrenceDateTime: z.string().optional(),
  method: CodeableConceptSchema.optional(),
  prediction: z
    .array(
      z.looseObject({
        outcome: CodeableConceptSchema,
        probabilityDecimal: z.number().min(0).max(1).optional(),
        extension: z.array(RiskExtensionSchema).optional(),
      }),
    )
    .optional(),
  extension: z.array(RiskExtensionSchema).optional(),
  note: z.array(z.looseObject({ text: z.string().optional() })).optional(),
});

export const BundleSchema = z.looseObject({
  resourceType: z.literal("Bundle"),
  total: z.number().int().nonnegative().optional(),
  entry: z.array(z.looseObject({ resource: z.unknown() })).optional(),
});

export const SessionSchema = z.object({
  authenticated: z.literal(true),
  user: z.object({ displayName: z.string().min(1).max(200) }),
  capabilities: z.object({
    canRead: z.boolean(),
    canWrite: z.boolean(),
    canDelete: z.boolean(),
  }),
  csrfToken: z.string().min(20),
  features: z.object({ experimentalMl: z.boolean() }),
});

export type FhirPatient = z.infer<typeof PatientSchema>;
export type FhirObservation = z.infer<typeof ObservationSchema>;
export type FhirEncounter = z.infer<typeof EncounterSchema>;
export type FhirComposition = z.infer<typeof CompositionSchema>;
export type FhirClinicalResource = z.infer<typeof ClinicalResourceSchema>;
export type FhirRiskAssessment = z.infer<typeof RiskAssessmentSchema>;
export type Session = z.infer<typeof SessionSchema>;
