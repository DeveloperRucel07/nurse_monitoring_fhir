# Frontend-Entscheidungen

Status: Entscheidungen in der React-Grundlage umgesetzt.

## 1. React als einziges Frontend

Der geprüfte Cutover ist abgeschlossen. React/Vite ist die einzige Benutzeroberfläche und Nginx liefert das Produktions-Bundle aus. Paralleler Python-UI-Code wurde entfernt; die Versionshistorie bleibt in Git nachvollziehbar.

## 2. Authentifizierung

### Optionen

- A: Keycloak Public SPA Client mit PKCE, Token nur im Speicher.
- B: FastAPI Backend-for-Frontend mit HTTP-only Session Cookie und serverseitigen Tokens.

### Empfehlung

B. Es erfüllt die gewünschte Token-Isolation und erlaubt Same-Origin-Betrieb. Rollen im Frontend steuern nur die Bedienoberfläche; das Backend bleibt Autorisierungsgrenze.

## 3. FHIR-Typisierung

### Optionen

- A: Umfangreiche generierte FHIR-Typbibliothek im Browser.
- B: Schmale, featurebezogene Zod-Schemas plus eigene Domainmodelle.

### Empfehlung

B. Das Bundle bleibt kleiner, ungültige Laufzeitdaten werden erkannt und UI-Komponenten bleiben von komplexen FHIR-Pfaden entkoppelt. Unbekannte Felder werden an der Grenze verworfen.

## 4. Server State

### Optionen

- A: Redux als globaler Store für API-Daten.
- B: TanStack Query für Server State; React State/Reducer nur für lokalen UI-Zustand.

### Empfehlung

B. Caching, Invalidierung und Fehlerzustände werden zentral gelöst, ohne klinische Daten unnötig zu duplizieren. Persistente Query-Plugins werden nicht eingesetzt.

## 5. Tabellen und Trends

- TanStack Table wird für Sortierung, Filter und spätere serverseitige Pagination der Patientenliste eingesetzt.
- Recharts wird für wenige klinische Zeitreihen eingesetzt.
- Virtualisierung wird erst ergänzt, wenn reale Messungen einen Bedarf zeigen.
- Diagramme erhalten explizite Einheiten, Zeitangaben, Datenlücken und eine tabellarische Alternative.

## 6. UI-Grundlage

Semantisches HTML und selektiv eingesetzte, barrierearme shadcn/Radix-Primitives bilden die Interaktionsbasis. Ein eigenes Token-System definiert Farben, Typografie, Abstände, Fokuszustände und Dichte; das generische Standard-Theme wird nicht übernommen. Fachkomponenten bleiben eigene Komponenten.

## 7. Styling

Empfohlen sind CSS Custom Properties und eine klar begrenzte Utility-/Komponentenstrategie. Keine dynamischen Inline-Styles aus API-Daten, kein HTML-Injection-Pfad und keine dekorative Bildwelt. Die Oberfläche ist eine ruhige klinische Arbeitsfläche mit Desktop-, Tablet- und Mobile-Layouts.

## 8. API Client und Fehler

Eine einzige Transportinstanz verwendet relative Same-Origin-Pfade, feste Timeouts und `credentials: "same-origin"`. Features verwenden typisierte Funktionen und keine direkten `fetch`-Aufrufe.

Fehler werden als Union modelliert:

```ts
type ApiError =
  | { kind: "unauthorized"; requestId?: string }
  | { kind: "forbidden"; requestId?: string }
  | { kind: "validation"; messages: string[]; requestId?: string }
  | { kind: "conflict"; requestId?: string }
  | { kind: "offline" }
  | { kind: "upstream"; requestId?: string }
  | { kind: "invalid-response"; requestId?: string };
```

OperationOutcome-Diagnosen werden begrenzt und als Text gerendert. Rohantworten werden nicht geloggt oder an Telemetrie übergeben.

## 9. Routen und Datenschutz

Der erste Entwurf hält den ausgewählten Patienten im flüchtigen Anwendungskontext und verwendet `/patient` statt `/patients/{fhirId}`. Dadurch landen direkte Identifikatoren nicht in Browserhistorie und Referrer-Informationen. Ein Seitenreload führt bewusst zurück zur Patientenauswahl.

## 10. Abhängigkeiten

Geplante Kernabhängigkeiten:

- React und React DOM;
- TypeScript und Vite;
- React Router;
- TanStack Query;
- Zod;
- TanStack Table für die geforderten Listenfunktionen;
- Recharts erst mit dem Trend-Modul;
- Lucide für konsistente, zugängliche Icons;
- Vitest, React Testing Library und DOM-Matcher für Tests.

Keine Analytics-, Session-Replay-, HTML-Sanitizing- oder globale Client-State-Library wird ohne konkreten Bedarf aufgenommen. Versionen werden bei Implementierungsbeginn geprüft und im Lockfile fixiert.

## 11. Umgesetzte Infrastruktur und offene Fachentscheidungen

- Redis dient als interner, nicht veröffentlichter Session Store; OAuth-Tokens werden vor Speicherung mit Fernet verschlüsselt.
- Patientensuche und Patienten-Kontextabfragen verwenden POST-Verträge ohne sensible URL-Parameter.
- Ein Dashboard-Aggregat fehlt weiterhin; nicht verfügbare Kennzahlen werden deshalb nicht errechnet oder erfunden.
- fachliche Terminologie und Einheitenkonvertierung;
- Mapping von Station und Zimmer;
- Aktivierung eines klinischen RiskAssessment-Modells — derzeit existiert ausschließlich der deaktivierte synthetische Demo-Modus.

Diese Punkte benötigen Backend- beziehungsweise fachliche Entscheidungen und werden nicht stillschweigend im Frontend gelöst.
