from datetime import datetime
from pathlib import Path
import sys

import streamlit as st

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from application.services import observations_from_bundle, patients_from_bundle, risks_from_assessment
from frontend.domain.models import Patient, parse_patient
from frontend.infrastructure.api_client import ApiError, FhirApiClient
from frontend.presentation.components import risk_card

st.set_page_config(page_title="Pflege-Monitoring", page_icon="✚", layout="wide", initial_sidebar_state="expanded")
st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Space+Mono&display=swap');
:root { --ink:#19323a; --muted:#6b7d80; --paper:#f4f7f5; --line:#dbe5e1; --teal:#2f7d68; --mint:#dceee7; --coral:#c2413b; }
html, body, [class*="css"] { font-family:'DM Sans',sans-serif; color:var(--ink); }
.stApp { background:var(--paper); }
.block-container { max-width:1220px; padding-top:2.5rem; }
[data-testid="stSidebar"] { background:#19323a; }
[data-testid="stSidebar"] * { color:#eff8f3; }
[data-testid="stSidebar"] .stCaption { color:#aec6bf; }
h1, h2, h3 { letter-spacing:0; }
.eyebrow { color:var(--teal); font:600 0.76rem 'Space Mono',monospace; letter-spacing:0; text-transform:uppercase; }
.hero { border-bottom:1px solid var(--line); padding-bottom:1.5rem; margin-bottom:1.5rem; }
.hero h1 { font-size:2.45rem; margin:.25rem 0 .35rem; }
.hero p { color:var(--muted); margin:0; }
.risk-card { background:white; border:1px solid var(--line); padding:1.15rem; margin:.5rem 0; border-radius:6px; }
.risk-heading { display:flex; justify-content:space-between; font-weight:600; font-size:1.02rem; }
.risk-heading strong { font-size:1.35rem; }
.risk-bar { background:#e9efec; height:7px; margin:.85rem 0 .65rem; border-radius:10px; overflow:hidden; }
.risk-bar span { display:block; height:100%; border-radius:10px; }
.risk-meta { display:flex; justify-content:space-between; gap:1rem; color:var(--muted); font-size:.78rem; }
.patient-chip { background:var(--mint); padding:.8rem 1rem; border-radius:6px; margin:.5rem 0 1rem; }
[data-testid="stMetric"] { background:white; border:1px solid var(--line); padding:1rem; border-radius:6px; }
</style>""", unsafe_allow_html=True)

client = FhirApiClient()
if "selected_patient" not in st.session_state:
    st.session_state.selected_patient = None


def api_call(action):
    try:
        return action()
    except ApiError as exc:
        st.error(str(exc))
        return None


def patient_label(patient: Patient) -> str:
    return f"{patient.display_name or 'Unbenannt'} · {patient.id}"


with st.sidebar:
    st.markdown("## ✚ Pflege-Monitoring")
    st.caption("FHIR · klinische Übersicht")
    page = st.radio("Bereich", ["Übersicht", "Patienten", "Patient aufnehmen"], label_visibility="collapsed")
    st.divider()
    st.caption("Datenschutzmodus aktiv")
    st.caption("Keine Gesundheitsdaten werden lokal gespeichert.")

if page == "Patient aufnehmen":
    st.markdown('<div class="eyebrow">Neuer Datensatz</div><div class="hero"><h1>Patient aufnehmen</h1><p>Erstelle einen neuen FHIR-Patienten für das Pflege-Monitoring.</p></div>', unsafe_allow_html=True)
    with st.form("create_patient"):
        first, last = st.columns(2)
        given = first.text_input("Vorname", max_chars=80)
        family = last.text_input("Nachname", max_chars=80)
        gender = st.selectbox("Geschlecht", ["female", "male", "other", "unknown"], format_func=lambda value: {"female":"Weiblich", "male":"Männlich", "other":"Divers", "unknown":"Nicht angegeben"}[value])
        birth_date = st.date_input("Geburtsdatum", value=datetime(1980, 1, 1), max_value=datetime.now())
        submitted = st.form_submit_button("Patient anlegen", type="primary", use_container_width=True)
    if submitted:
        if not given.strip() or not family.strip():
            st.warning("Vor- und Nachname sind erforderlich.")
        else:
            result = api_call(lambda: client.create_patient(given, family, gender, birth_date.isoformat()))
            if result:
                st.session_state.selected_patient = result.get("id")
                st.success("Patient wurde angelegt.")
                st.info("Wechsle zu Patienten, um Beobachtungen und Risiken zu erfassen.")

elif page == "Patienten":
    st.markdown('<div class="eyebrow">Patientenakte</div><div class="hero"><h1>Patienten</h1><p>Suche und öffne eine sichere, fokussierte Patientenansicht.</p></div>', unsafe_allow_html=True)
    query = st.text_input("Nachname suchen", placeholder="z. B. Mustermann")
    bundle = api_call(lambda: client.list_patients(query))
    patients = patients_from_bundle(bundle or {})
    if not patients:
        st.info("Keine Patienten gefunden.")
    else:
        options = {patient_label(patient): patient.id for patient in patients}
        current = st.session_state.selected_patient
        default_index = next((index for index, patient_id in enumerate(options.values()) if patient_id == current), 0)
        selected_label = st.selectbox("Patient auswählen", list(options), index=default_index)
        st.session_state.selected_patient = options[selected_label]
        st.rerun()

else:
    selected_id = st.session_state.selected_patient
    if not selected_id:
        st.markdown('<div class="eyebrow">Pflege-Leitstand</div><div class="hero"><h1>Guten Morgen.</h1><p>Wähle links einen Patienten aus, um Beobachtungen und Pflegerisiken zu sehen.</p></div>', unsafe_allow_html=True)
        st.info("Noch kein Patient ausgewählt. Öffne den Bereich Patienten.")
    else:
        patient_data = api_call(lambda: client.get_patient(selected_id))
        observation_data = api_call(lambda: client.list_observations(selected_id))
        patient = parse_patient(patient_data) if patient_data else None
        observations = observations_from_bundle(observation_data or {})
        if patient:
            st.markdown(f'<div class="eyebrow">Pflege-Leitstand · {patient.id}</div><div class="hero"><h1>{patient.display_name or "Unbenannter Patient"}</h1><p>Persönliche Daten · {patient.birth_date} · {patient.gender}</p></div>', unsafe_allow_html=True)
            left, right = st.columns([1.1, 1.9], gap="large")
            with left:
                st.subheader("Pflegerisiken")
                assessment = api_call(lambda: client.assess_risks(patient.id))
                if assessment:
                    for risk in risks_from_assessment(assessment):
                        risk_card(risk.label, risk.probability, risk.status, risk.missing_features)
                    st.caption("Automatisierte Einschätzung auf Basis verfügbarer FHIR-Daten. Sie ersetzt keine professionelle Pflegeeinschätzung.")
            with right:
                st.subheader("Aktuelle Beobachtungen")
                if observations:
                    for observation in sorted(observations, key=lambda item: item.effective, reverse=True):
                        st.markdown(f"**{observation.display}**  \n{observation.value} · {observation.effective}")
                        st.divider()
                else:
                    st.info("Noch keine Beobachtungen vorhanden.")
                with st.expander("Observation erfassen"):
                    with st.form("create_observation"):
                        presets = {"Herzfrequenz":"8867-4", "Körpertemperatur":"8310-5", "Atemfrequenz":"9279-1", "Sauerstoffsättigung":"2708-6", "Blutdruck systolisch":"8480-6"}
                        display = st.selectbox("Messgröße", list(presets))
                        value = st.number_input("Wert", min_value=0.0, step=0.1)
                        unit = st.text_input("Einheit", value="/min", max_chars=20)
                        effective = st.date_input("Datum", value=datetime.now()).isoformat() + "T09:00:00+00:00"
                        save_observation = st.form_submit_button("Observation speichern", type="primary")
                    if save_observation:
                        result = api_call(lambda: client.create_observation(patient.id, presets[display], display, value, unit, effective))
                        if result:
                            st.success("Observation gespeichert.")
                            st.rerun()
