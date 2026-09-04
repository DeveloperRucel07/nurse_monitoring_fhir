# FHIR-zu-Frontend-Mapping

Status: React-Mapping und sichere Pflege-Schreibverträge implementiert.

## Tatsächlich verfügbare Ressourcen

| Ressource | Lesen | Schreiben | Aktueller Backend-Pfad | Einschränkung |
| --- | --- | --- | --- | --- |
| `Patient` | Liste/Detail | Create, Update, Delete | `/Patient`, `/Patient/{id}` | Aufnahme-Workflow erzeugt zusätzlich eine stabile organisationslokale Kennung. |
| `Encounter` | patientenbezogene Liste | Atomar mit Aufnahme | `/ui/patients/admit`, `/ui/patient/encounters` | Aktiver stationärer Fall mit stabiler Fallkennung; Location/Station ist noch nicht angebunden. |
| `Composition` | patientenbezogene Liste | Create, Korrektur, entered-in-error | `/ui/patient/nursing-reports*` | Pflegebericht mit LOINC `34746-8`, Autor, Encounter, FHIR-Version und optimistischer Nebenläufigkeitskontrolle. |
| `Observation` | Liste/Detail | Create, Status-Patch, Delete | `/Observation`, `/Observation/{id}` | Rohe FHIR-Antwort; keine Response-Schemas in OpenAPI. |
| `Condition` | patientenbezogene Liste | Create | `/Patient/{id}/clinical-records/Condition` | Generisches, vereinfachtes Schreibmodell. |
| `CarePlan` | patientenbezogene Liste | Create | `/Patient/{id}/clinical-records/CarePlan` | Generisches Schreibmodell bildet CarePlan nur teilweise ab. |
| `MedicationRequest` | Nein | Nein | nicht vorhanden | Seed-Daten existieren, aber kein API-Vertrag. Backend unterstützt stattdessen `MedicationStatement`. |
| `Procedure` | Nein | Nein | nicht vorhanden | Seed-Daten existieren, aber kein API-Vertrag. |
| `AllergyIntolerance` | patientenbezogene Liste | Create | `/Patient/{id}/clinical-records/AllergyIntolerance` | Generisches, vereinfachtes Schreibmodell. |
| `RiskAssessment` | aktuelle Berechnung | Nein | `/Patient/{id}/nursing-risk-assessment` | Standardmäßig deaktivierte synthetische Demo; nicht persistiert, keine Historie. |

Zusätzlich unterstützt der generische Pfad derzeit `MedicationStatement` und `ClinicalImpression`. Diese Typen dürfen nicht stillschweigend als `MedicationRequest` beziehungsweise `Procedure` umgedeutet werden.

## Pflege-Schreibverträge

Das React-Frontend verwendet für klinische Schreibvorgänge schmale UI-Endpunkte. Die Patienten-ID wird im Request-Body und nicht in einer URL oder Browserhistorie übertragen.

| Funktion | UI-Endpunkt | FHIR-Ergebnis | Sicherheitsgrenze |
| --- | --- | --- | --- |
| Vitalparameter erfassen | `POST /ui/patient/vital-measurements` | `Observation` | Messart wird serverseitig auf feste LOINC-/UCUM-Werte abgebildet; Wertebereiche, Zeitzone und Patient-ID werden serverseitig validiert. |
| Pflegebericht schreiben | `POST /ui/patient/nursing-reports` | `Composition` | LOINC `34746-8`, Autor aus verifizierter Sitzung, aktiver Encounter und serverseitig escaped XHTML Narrative. |
| Pflegebericht korrigieren | `PUT /ui/patient/nursing-reports` | neue Version derselben `Composition` | `If-Match`/`meta.versionId`; nur Autor oder `pflege_admin`; Status `amended`. |
| Pflegebericht als fehlerhaft markieren | `POST /ui/patient/nursing-reports/entered-in-error` | neue Version derselben `Composition` | Kein Löschen; Status `entered-in-error` und verpflichtender Grund. |
| Patient aufnehmen | `POST /ui/patients/admit` | atomare Transaktion aus `Patient` und `Encounter` | Servergenerierte Patienten- und Fallkennung; entweder beide Ressourcen werden gespeichert oder keine. |

Die Eingabegrenzen für Vitalwerte sind Schutz gegen Übertragungs- und Eingabefehler, keine klinischen Normalbereiche und keine automatische Bewertung. Autorisierung, FHIR-Validierung und Code-/Einheitenzuordnung bleiben Backend-Aufgaben.

Die generischen Roh-FHIR-Schreibpfade für `Patient`, `Observation` und klinische Ressourcen sind auf `pflege_admin` begrenzt. `pflege_write` darf klinische Daten ausschließlich über die engen, serverseitig gemappten Pflegeverträge erzeugen und kann deren Terminologie daher nicht über manipulierte Browseranfragen ersetzen.

## Synthetische Entwicklungsdaten

Der Generator `backend/app/local_test/seed.py` erzeugt jeden synthetischen Patienten zusammen mit einem aktiven stationären `Encounter` in derselben FHIR-Transaktion. Beide Ressourcen erhalten einen offiziellen Identifier aus den konfigurierten Systemen `PATIENT_IDENTIFIER_SYSTEM` und `ENCOUNTER_IDENTIFIER_SYSTEM`. Die sichtbaren Werte folgen den Formaten `PAT-SEED-000001` und `FALL-SEED-000001`.

Der Generator ist für eine leere lokale Entwicklungsdatenbank vorgesehen. Dadurch kann das React-Frontend unmittelbar nach dem Seed eine Patienten- und Fallnummer anzeigen sowie Vitalmessungen und Pflegeberichte dem aktiven Fall zuordnen.

## Vitalzeichen-Codes im Bestand

Die folgenden Codes werden vom bestehenden Backend beziehungsweise Seed verwendet. Ihre fachliche Terminologie und Einheiten werden in einem späteren Mapping-Schritt separat validiert; das Frontend übernimmt sie nicht unkritisch als universell gültig.

| Domänenwert | Code im Bestand | Struktur |
| --- | --- | --- |
| Herzfrequenz | LOINC `8867-4` | `Observation.valueQuantity` |
| Blutdruck-Panel | LOINC `85354-9` | `Observation.component` |
| Systolisch | LOINC `8480-6` | Component `valueQuantity` |
| Diastolisch | LOINC `8462-4` | Component `valueQuantity` |
| Körpertemperatur | LOINC `8310-5` | `Observation.valueQuantity` |
| Mobilität | LOINC `83186-7` | `valueCodeableConcept` mit `LA12302-8`, `LA12303-6` oder `LA12304-4` |
| Sturzanamnese im Morse-Kontext | LOINC `59454-9` | `valueCodeableConcept` mit `LA32-8` oder `LA33-6` |
| Morse-Gesamtscore | LOINC `59460-6` | `Observation.valueQuantity` |
| Morse-Risikostufe | LOINC `59461-4` | `Observation.valueCodeableConcept` |
| Morse-Gangbild | LOINC `59458-0` | `Observation.valueCodeableConcept` |

Die Sturzanamnese bezieht sich ausdrücklich auf „unmittelbar oder innerhalb von drei Monaten“ im Morse-Kontext. Sie wird als eigener Messwert dokumentiert und nicht aus dem Gesamtscore abgeleitet.

## Schmale FHIR DTOs

Das React-Projekt soll keine vollständige FHIR-Spezifikation nachbauen. Für jede verwendete Ressource wird ein minimales Zod-Schema definiert, das nur benötigte Felder übernimmt und unbekannte Felder verwirft.

Beispielhafte Grenzen:

```ts
type FhirObservationDto = {
  resourceType: "Observation";
  id?: string;
  status: string;
  code: FhirCodeableConceptDto;
  subject?: FhirReferenceDto;
  effectiveDateTime?: string;
  effectivePeriod?: { start?: string; end?: string };
  issued?: string;
  valueQuantity?: FhirQuantityDto;
  valueCodeableConcept?: FhirCodeableConceptDto;
  component?: FhirObservationComponentDto[];
};
```

Die Runtime-Schemas prüfen Typen, zulässige Größen und kritische Referenzformen. Ein TypeScript-Cast ersetzt diese Prüfung nicht.

## Domain-Ergebnisse

Mapper geben diskriminierte Ergebnisse zurück:

```ts
type MappingResult<T> =
  | { kind: "complete"; value: T }
  | { kind: "partial"; value: T; missing: ClinicalField[] }
  | { kind: "unsupported"; reason: string }
  | { kind: "invalid"; errorCode: string };
```

Beispiel für Vitalwerte:

```ts
type VitalSign =
  | {
      kind: "heart-rate" | "temperature";
      value: number;
      unit: string;
      measuredAt: string;
      status: string;
      sourceId?: string;
    }
  | {
      kind: "blood-pressure";
      systolic?: number;
      diastolic?: number;
      unit?: string;
      measuredAt: string;
      status: string;
      sourceId?: string;
    };
```

Ein partieller Blutdruck bleibt partiell. Fehlende systolische oder diastolische Werte werden nicht mit `0` ergänzt.

## Auswahl und Darstellung

- `cancelled` und `entered-in-error` werden nicht als aktuelle klinische Messwerte dargestellt.
- Die neueste verwendbare Messung wird nach `effectiveDateTime`, `effectivePeriod`, `issued` und `meta.lastUpdated` bestimmt; die bestehende Backendlogik ist Referenz.
- Einheiten werden immer zusammen mit dem Wert angezeigt. Unbekannte oder widersprüchliche Einheiten werden als Datenqualitätsproblem markiert, nicht automatisch konvertiert.
- Ungültige Zeitstempel ergeben „Zeitpunkt nicht verfügbar“ und keinen erfundenen aktuellen Zeitpunkt.
- Charts verbinden keine Datenlücken und erhalten eine sichtbare Einheit sowie eine nicht irreführende Achsenskalierung.
- FHIR Narrative HTML wird nicht gerendert.

## RiskAssessment

Der aktuelle Vertrag liefert:

- `status = preliminary`;
- Berechnungszeitpunkt;
- Outcome-Code;
- optionalen synthetischen Modellwert;
- Status und fehlende Features über Extensions;
- Kennzeichnungen `demonstration-only`, `not-clinically-validated` und `synthetic`;
- einen klaren Warnhinweis.

Nicht verfügbar sind Assessment-ID, persistierte Historie, Modellversion, verwendete Features, Quellenreferenzen und belastbare klinische Risikostufen. Die UI zeigt diese Felder daher als „Nicht vom Backend bereitgestellt“ oder lässt sie aus; sie leitet sie nicht aus anderen Daten ab.

## Clinical Timeline

Eine pure Mapping-Schicht transformiert jede unterstützte Ressource in ein gemeinsames Ereignismodell und sortiert anschließend nach klinischem Zeitpunkt. Der Ressourcentyp bleibt erhalten; `MedicationStatement` wird beispielsweise nicht als `MedicationRequest` beschriftet. Ressourcen ohne sicheren Zeitpunkt erscheinen in einem getrennten Abschnitt „Zeitpunkt nicht verfügbar“.
