# Frontend Security & Privacy Architecture

Status: Kernkontrollen für das React-Frontend implementiert; externe Penetrationstests und fachliche Freigabe stehen aus.

## Aktuelle Schutzmaßnahmen

- HAPI FHIR und Datenbanken sind nur in internen Docker-Netzen erreichbar.
- Das Backend verlangt für alle Fachdaten ein signiertes Keycloak-Access-Token.
- Issuer, Audience, autorisierter Client, Signaturalgorithmus, Token-Typ und Rollen werden geprüft.
- Schreib- und Löschrechte werden serverseitig getrennt.
- Auditlogs verwenden Route Templates statt konkreter Patient-IDs und protokollieren keine Request Bodies oder Tokens.
- Der React-Produktionscontainer liefert statische Assets und vermittelt Same-Origin-Aufrufe an das Backend.
- OAuth-Tokens liegen verschlüsselt im internen Redis-Session-Store und werden nie an React ausgeliefert.

## Ursprünglich festgestellte Lücken und Status

| Priorität | Befund | Auswirkung |
| --- | --- | --- |
| Erledigt | Das Keycloak-Frontend ist ein Confidential Client mit Secret. | Das Secret bleibt im BFF und gelangt nicht ins Browserbundle. |
| Erledigt | Es fehlte eine HTTP-only Session und ein BFF-Vertrag. | Redis-Session, PKCE, `state`, `nonce`, CSRF und Zeitgrenzen sind implementiert. |
| Erledigt | Patientensuche verwendete Name und Geburtsdatum als GET-Query-Parameter. | UI-Such- und Kontextendpunkte verwenden JSON-Bodies. |
| Erledigt | Keycloak `webOrigins` war auf `+` gesetzt. | Die Origin wird auf `APP_ORIGIN` begrenzt. |
| Erledigt | Security Header fehlten. | Der Nginx-Gateway setzt CSP, Frame-, MIME-, Referrer- und Permissions-Schutz. |
| Mittel | API-Fehler haben gemischte Formen: `OperationOutcome` und `{detail}`. | UI könnte unsichere Rohdiagnosen oder inkonsistente Zustände anzeigen. |
| Mittel | Klinische GET-Antworten haben überwiegend kein explizites `no-store`. | Browser- oder Proxy-Caching ist nicht ausreichend ausgeschlossen. |
| Mittel | Das Backend hat keine Browser-CORS-Konfiguration. | Direkter SPA-Zugriff funktioniert nicht sicher; pauschales CORS wäre riskant. |

## Authentifizierungsentscheidung

### Option A: Public SPA Client mit Authorization Code und PKCE

Vorteile: geringe Backend-Erweiterung, Standard-Spa-Flow.

Nachteile: Access- und gegebenenfalls Refresh-Tokens bleiben für JavaScript erreichbar; XSS hat dadurch größere Auswirkungen. Session-Erneuerung, Tab-Synchronisierung und Token-Löschung werden komplexer.

### Option B: Backend-for-Frontend mit serverseitiger OAuth-Session

Vorteile: keine OAuth-Tokens im Browser, Confidential-Client-Secret bleibt serverseitig, Same-Origin-Betrieb vermeidet CORS, zentrale Session-Inaktivität und serverseitiger Logout sind möglich.

Nachteile: benötigt Session Store, Auth-Routen und CSRF-Schutz für Cookie-basierte Mutationen.

### Empfehlung

Option B. Für Gesundheitsdaten überwiegen Token-Isolation, zentrale Kontrolle und eine kleinere Browser-Vertrauensbasis den zusätzlichen Backend-Aufwand.

## Zielkontrollen

### Session

- zufällige, rotierbare Session-ID in einem Cookie mit `HttpOnly`, `Secure`, `SameSite=Lax`, `Path=/` und `__Host-`-Präfix;
- Access- und Refresh-Tokens ausschließlich verschlüsselt im serverseitigen Session Store;
- Authorization Code Flow mit PKCE, `state` und `nonce`;
- kurze Inaktivitätsgrenze, absolute Sitzungsgrenze und serverseitige Invalidierung beim Logout;
- keine Tokens oder Patientendaten in Web Storage;
- Logout-Signal zwischen Tabs enthält ausschließlich ein Ereignis, keine Identität oder PHI.

### CSRF und CORS

- Same-Origin-Auslieferung für React und API;
- CSRF-Token, der an die Session gebunden und bei jeder zustandsändernden Anfrage als Header verlangt wird;
- zusätzliche Prüfung von `Origin` beziehungsweise `Referer` für Mutationen;
- keine wildcard Origins und keine Credential-CORS-Freigabe an fremde Origins;
- GET bleibt nebenwirkungsfrei.

### XSS und Darstellung

- kein `dangerouslySetInnerHTML` für FHIR- oder Benutzerdaten;
- React-Textknoten für dynamische Inhalte;
- keine HTML-Darstellung von FHIR Narrative (`resource.text.div`) ohne einen gesonderten, streng geprüften Sanitizing-Vertrag;
- CSP ohne `unsafe-eval` und ohne Inline-Skripte im Produktionsbuild; `unsafe-inline` ist aktuell ausschließlich für Styles nötig, weil die Diagrammbibliothek Laufzeit-Styles setzt;
- keine dynamisch konstruierten Skript-, Bild- oder Linkziele aus FHIR-Daten.

### Empfohlene Produktionsheader

```text
Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'
Referrer-Policy: no-referrer
X-Content-Type-Options: nosniff
Permissions-Policy: camera=(), microphone=(), geolocation=(), payment=(), usb=()
Cross-Origin-Opener-Policy: same-origin
Cache-Control: no-store
```

HSTS wird nur am echten TLS-Endpunkt aktiviert. Gehashte statische Assets dürfen separat langfristig gecacht werden; HTML, Auth- und Fachdatenantworten nicht.

### Datenschutz

- Browser-Routen enthalten weder Name noch Geburtsdatum noch direkte FHIR-ID.
- Die neuen UI-Endpunkte übertragen FHIR-IDs und Suchkriterien ausschließlich in JSON-Bodies; sie erscheinen nicht in URL, Browserhistorie oder Access-Logs.
- Die Patientensuche verwendet einen datensparsamen Body-basierten BFF-Vertrag.
- kein Analytics-, Session-Replay- oder Error-Tracking-SDK mit Zugriff auf DOM oder Netzwerkpayloads;
- Fehlertelemetrie enthält nur Fehlerklasse, Status, Route Template, Build-Version und serverseitige Request-ID;
- Query Cache wird auf `401`, `403`, Logout und Nutzerwechsel gelöscht;
- kein Service Worker und kein Offline-Cache klinischer Antworten;
- keine Copy-Schaltflächen für Patientendaten; ein optionaler Sichtschutzmodus maskiert Identifikatoren.

## Autorisierung

Das Frontend erhält vom BFF nur abgeleitete Fähigkeiten, beispielsweise `canRead`, `canWrite`, `canDelete`, nicht das Access Token. UI-Elemente dürfen anhand dieser Fähigkeiten ausgeblendet oder deaktiviert werden. Jede Entscheidung bleibt zusätzlich im Backend erzwungen.

| Fähigkeit | Backend-Rollen |
| --- | --- |
| Lesen | `pflege_read`, `pflege_write`, `pflege_delete`, `pflege_admin` |
| Schreiben | `pflege_write`, `pflege_admin` |
| Löschen | `pflege_delete`, `pflege_admin` |

Bei `401` oder `403` werden klinische Ansichten sofort ersetzt und alle Query-Daten entfernt. Ein `403` darf nicht lediglich als Toast über weiterhin sichtbaren Patientendaten erscheinen.

## Security-Testschwerpunkte

- Redirect auf Login ohne Sitzung und Rückkehr nur nach gültigem `state`/`nonce`;
- kein Token in Bundle, DOM, URL oder Web Storage;
- Cache-Löschung und Entfernung klinischer UI bei `401`, `403`, Logout und Session-Ablauf;
- CSRF-Ablehnung ohne beziehungsweise mit falschem Token;
- Rollenmatrix für Lesen, Schreiben und Löschen;
- XSS-Payloads in Namen, Coding Displays, Notizen und `OperationOutcome` werden als Text gerendert;
- manipulierte Patientenreferenzen und fremde Patientenzugriffe werden serverseitig abgewiesen;
- CSP- und Security-Header-Tests am Produktionscontainer;
- keine PHI in Browser-Logs, Telemetrie oder Query-Strings.
