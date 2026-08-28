# Pflege-Monitoring Dashboard

Streamlit frontend for the FastAPI/FHIR backend.

## Start

From the repository root:

```powershell
$env:BACKEND_API_URL = "http://localhost:8000"
streamlit run frontend/app.py
```

Optional: set `BACKEND_API_TOKEN` when the backend is configured to require a bearer token. The dashboard does not persist patient data locally and sends requests only through the backend API.
