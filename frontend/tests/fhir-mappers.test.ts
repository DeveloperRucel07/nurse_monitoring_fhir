import { describe, expect, it } from "vitest";
import { mapBundle, mapObservation, mapPatient } from "../src/shared/fhir/mappers";

describe("FHIR mapper", () => {
  it("stellt fehlende klinische Werte nicht als Nullwert dar", () => {
    const observation = mapObservation({
      resourceType: "Observation",
      status: "final",
      code: { coding: [{ system: "http://loinc.org", code: "8867-4" }] },
    });

    expect(observation.kind).toBe("heart-rate");
    expect(observation.value).toBeUndefined();
    expect(observation.measuredAt).toBeUndefined();
  });

  it("verwirft ungültige Bundle-Einträge explizit", () => {
    const result = mapBundle(
      {
        resourceType: "Bundle",
        entry: [
          { resource: { resourceType: "Patient", id: "1", name: [{ family: "Muster" }] } },
          { resource: { resourceType: "Patient", name: [{ family: "Ohne ID" }] } },
        ],
      },
      mapPatient,
    );

    expect(result.items).toHaveLength(1);
    expect(result.rejectedCount).toBe(1);
  });

  it("ignoriert zukünftige Geburtsdaten bei der Altersberechnung", () => {
    const patient = mapPatient({ resourceType: "Patient", id: "1", birthDate: "2999-01-01" });
    expect(patient.age).toBeUndefined();
  });
});
