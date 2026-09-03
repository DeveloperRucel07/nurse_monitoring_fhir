# Pflege-Monitoring Dashboard

Streamlit frontend for the authenticated FastAPI/FHIR backend.

## Start

Use Docker Compose from the repository root so Keycloak, the runtime-only OIDC
configuration, and the backend are configured together:

```powershell
Copy-Item .env.example .env
docker compose up --build
```

Opening http://localhost:8501 without an active session redirects directly to
Keycloak. The access token is taken from the authenticated Streamlit session and
is never configured as a static environment token. The dashboard does not
persist patient data locally and sends clinical requests only through the
backend API.
