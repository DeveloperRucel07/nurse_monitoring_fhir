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

Benutzer mit der Rolle `pflege_write` können im React-Frontend Patienten aufnehmen, unterstützte Vitalparameter dokumentieren und Pflegeberichte als FHIR `ClinicalImpression` speichern. Benutzer mit reinen Leserechten sehen keine Schreibformulare. Das Backend prüft die Rolle bei jeder Mutation erneut und ordnet Vitalparameter ausschließlich über fest definierte LOINC-/UCUM-Mappings zu.

Die Patientenaufnahme erzeugt aktuell nur die logische FHIR-ID. Eine organisationsweit stabile Patienten- oder Fallnummer ist noch nicht implementiert; die Oberfläche weist deshalb vor dem Speichern auf Identitäts- und Dublettenprüfung hin.

## Lokale Frontend-Prüfungen

```powershell
cd frontend
npm.cmd ci
npm.cmd run lint
npm.cmd test
npm.cmd run build
```
