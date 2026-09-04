# CareSignal – React FHIR Monitoring

Sicheres React-/TypeScript-Frontend für das authentifizierte FastAPI-/FHIR-Backend.

## Start

Use Docker Compose from the repository root so Keycloak, the runtime-only OIDC
configuration, and the backend are configured together:

```powershell
Copy-Item .env.example .env
docker compose up --build
```

Vor dem ersten Start muss `BFF_SESSION_ENCRYPTION_KEY` als Fernet-Schlüssel gesetzt werden:

```powershell
.\.venv\Scripts\python.exe -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Den ausgegebenen Wert in `.env` übernehmen. Für lokalen HTTP-Betrieb bleibt
`BFF_COOKIE_SECURE=false`; an einem TLS-Endpunkt muss der Wert `true` sein.

Der Aufruf von http://localhost:8501 ohne aktive Sitzung führt direkt über den
serverseitigen Authorization-Code-/PKCE-Flow zu Keycloak. OAuth-Tokens und das
Client-Secret erreichen den Browser nicht. Klinische Daten werden nicht in Web
Storage persistiert; Patientenkontexte und Suchkriterien stehen nicht in URLs.

## Pflegefunktionen

Benutzer mit der Rolle `pflege_write` können im React-Frontend Patienten samt aktivem FHIR `Encounter` aufnehmen, Vitalparameter, Mobilität und Sturzanamnese dokumentieren und Pflegeberichte als FHIR `Composition` speichern. Benutzer mit reinen Leserechten sehen keine Schreibformulare. Das Backend prüft die Rolle bei jeder Mutation erneut und ordnet Assessments ausschließlich über fest definierte LOINC-/UCUM-Mappings zu.

Die Aufnahme erzeugt serverseitig eine stabile organisationslokale Patienten- und Fallkennung und speichert Patient und Encounter atomar. Pflegeberichte sind an den aktiven Fall und den angemeldeten Autor gebunden. Korrekturen erzeugen über `If-Match` eine neue FHIR-Version; fehlerhafte Berichte werden nicht gelöscht, sondern nachvollziehbar als `entered-in-error` markiert.

## Lokale Frontend-Prüfungen

```powershell
cd frontend
npm.cmd ci
npm.cmd run lint
npm.cmd test
npm.cmd run build
```
