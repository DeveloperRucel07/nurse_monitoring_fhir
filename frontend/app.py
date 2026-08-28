from datetime import datetime
from pathlib import Path
import sys

import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from application.services import observations_from_bundle, patients_from_bundle, risks_from_assessment
from frontend.domain.models import Patient, parse_patient, parse_observation
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


def observation_status_label(status: str) -> str:
    labels = {
        "registered": "Erfasst",
        "preliminary": "Vorläufig",
        "final": "Abgeschlossen",
        "amended": "Ergänzt",
        "corrected": "Korrigiert",
        "cancelled": "Abgebrochen",
        "entered-in-error": "Fehlerhaft erfasst",
        "unknown": "Unbekannt",
    }
    return labels.get(status, status or "Unbekannt")


def show_observation_details(resource: dict) -> None:
    observation = parse_observation(resource)
    st.subheader(observation.display)
    value, effective, status = st.columns(3)
    value.metric("Messwert", observation.value)
    effective.metric("Zeitpunkt", observation.effective)
    status.metric("Status", observation_status_label(str(resource.get("status", ""))))
    patient_reference = resource.get("subject", {}).get("reference")
    if patient_reference:
        st.caption(f"Patient: {patient_reference.replace('Patient/', 'Patientennummer ')}")
    if resource.get("note"):
        note_text = " ".join(note.get("text", "") for note in resource["note"])
        if note_text:
            st.info(note_text)


def observation_series(resources: list[dict]) -> dict[str, list[tuple[datetime, float]]]:
    series: dict[str, list[tuple[datetime, float]]] = {}
    for resource in resources:
        effective = resource.get("effectiveDateTime")
        if not effective:
            continue
        try:
            measured_at = datetime.fromisoformat(effective.replace("Z", "+00:00"))
        except ValueError:
            continue
        coding = ((resource.get("code") or {}).get("coding") or [{}])[0]
        label = coding.get("display") or coding.get("code") or "Messwert"
        values = [(label, (resource.get("valueQuantity") or {}).get("value"))]
        if resource.get("component"):
            values = []
            for component in resource["component"]:
                component_coding = ((component.get("code") or {}).get("coding") or [{}])[0]
                component_label = component_coding.get("display") or component_coding.get("code") or "Messwert"
                values.append((component_label, (component.get("valueQuantity") or {}).get("value")))
        for value_label, value in values:
            if isinstance(value, (int, float)):
                series.setdefault(value_label, []).append((measured_at, float(value)))
    return series


def show_observation_chart(resources: list[dict]) -> None:
    series = observation_series(resources)
    if not series:
        st.info("Für diesen Patienten liegen noch keine zeitlich darstellbaren Messwerte vor.")
        return
    choices = list(series)
    selected = st.multiselect("Messwerte für den Verlauf", choices, default=choices)
    if not selected:
        st.caption("Wähle mindestens einen Messwert aus.")
        return
    chart = go.Figure()
    for label in selected:
        points = sorted(series[label])
        chart.add_trace(go.Scatter(
            x=[point[0] for point in points],
            y=[point[1] for point in points],
            mode="lines+markers",
            name=label,
        ))
    chart.update_layout(
        height=380,
        margin={"l": 10, "r": 10, "t": 20, "b": 10},
        legend_title_text="Messwerte",
        xaxis_title="Zeitpunkt",
        yaxis_title="Wert",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="white",
    )
    st.plotly_chart(chart, use_container_width=True, config={"displayModeBar": False})


def report_items(bundle: dict, record_type: str) -> list[str]:
    resources = [entry["resource"] for entry in bundle.get("entry", []) if entry.get("resource")]
    return [clinical_record_label(record_type, resource) for resource in resources]


def show_patient_report(patient: Patient, resources: list[dict]) -> None:
    st.subheader("Patientenbericht")
    assessment = api_call(lambda: client.assess_risks(patient.id))
    diagnoses = report_items(api_call(lambda: client.list_clinical_records(patient.id, "Condition")) or {}, "Condition")
    medications = report_items(api_call(lambda: client.list_clinical_records(patient.id, "MedicationStatement")) or {}, "MedicationStatement")
    allergies = report_items(api_call(lambda: client.list_clinical_records(patient.id, "AllergyIntolerance")) or {}, "AllergyIntolerance")
    care_plans = report_items(api_call(lambda: client.list_clinical_records(patient.id, "CarePlan")) or {}, "CarePlan")
    latest = sorted(resources, key=lambda resource: resource.get("effectiveDateTime", ""), reverse=True)[:5]
    lines = [
        f"Patient: {patient.display_name or 'Unbenannt'}",
        f"Geburtsdatum: {patient.birth_date}",
        f"Geschlecht: {patient.gender}",
        "",
        "Diagnosen: " + (", ".join(diagnoses) if diagnoses else "Keine dokumentiert"),
        "Medikamente: " + (", ".join(medications) if medications else "Keine dokumentiert"),
        "Allergien: " + (", ".join(allergies) if allergies else "Keine dokumentiert"),
        "Pflegeplan: " + (", ".join(care_plans) if care_plans else "Keine Maßnahmen dokumentiert"),
        "",
        "Letzte Messwerte:",
    ]
    lines.extend(
        f"- {parse_observation(resource).display}: {parse_observation(resource).value} ({parse_observation(resource).effective})"
        for resource in latest
    )
    if assessment:
        lines.append("")
        lines.append("Pflegerisiken:")
        lines.extend(
            f"- {risk.label}: {risk.probability:.0%}" if risk.probability is not None else f"- {risk.label}: Daten unvollständig"
            for risk in risks_from_assessment(assessment)
        )
    st.text_area("Zusammenfassung", "\n".join(lines), height=420, disabled=True)


def clinical_record_label(record_type: str, resource: dict) -> str:
    if record_type == "Condition":
        return resource.get("code", {}).get("text") or "Diagnose"
    if record_type == "MedicationStatement":
        return resource.get("medicationCodeableConcept", {}).get("text") or "Medikament"
    if record_type == "AllergyIntolerance":
        return resource.get("code", {}).get("text") or "Allergie"
    if record_type == "ClinicalImpression":
        return resource.get("summary") or "Pflegebericht"
    return resource.get("title") or "Pflegeplan"


def clinical_record_panel(
    patient_id: str,
    record_type: str,
    label: str,
    statuses: list[str],
    details_label: str,
) -> None:
    with st.form(f"create_{record_type}"):
        display = st.text_input(label)
        code, system = st.columns(2)
        terminology_code = code.text_input("Code (optional)")
        terminology_system = system.text_input("Codesystem", value="http://snomed.info/sct")
        details = st.text_area(details_label, max_chars=4000)
        status = st.selectbox("Status", statuses)
        submitted = st.form_submit_button("Speichern", type="primary")
    if submitted:
        if not display.strip():
            st.warning(f"{label} ist erforderlich.")
        elif api_call(lambda: client.create_clinical_record(patient_id, record_type, display, terminology_code, terminology_system, status, details)):
            st.success("Eintrag gespeichert.")
            st.rerun()

    bundle = api_call(lambda: client.list_clinical_records(patient_id, record_type))
    records = [entry["resource"] for entry in (bundle or {}).get("entry", []) if entry.get("resource")]
    if records:
        for resource in records:
            st.markdown(f"**{clinical_record_label(record_type, resource)}**")
            if resource.get("description"):
                st.caption(resource["description"])
            st.caption(f"Status: {resource.get('status', resource.get('clinicalStatus', {}).get('coding', [{}])[0].get('code', 'unbekannt'))}")
            st.divider()
    else:
        st.caption("Noch keine Einträge vorhanden.")


with st.sidebar:
    st.markdown("## ✚ Pflege-Monitoring")
    st.caption("FHIR · klinische Übersicht")
    page = st.radio("Bereich", ["Übersicht", "Patienten", "Patient aufnehmen", "Observationen"], label_visibility="collapsed")
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
    family, given, birthdate = st.columns(3)
    family_name = family.text_input("Nachname", placeholder="z. B. Mustermann")
    given_name = given.text_input("Vorname")
    birth_date = birthdate.text_input("Geburtsdatum", placeholder="JJJJ-MM-TT")
    bundle = api_call(lambda: client.list_patients(family_name, given_name, birth_date))
    patients = patients_from_bundle(bundle or {})
    if not patients:
        st.info("Keine Patienten gefunden.")
    else:
        options = {patient_label(patient): patient.id for patient in patients}
        current = st.session_state.selected_patient
        default_index = next((index for index, patient_id in enumerate(options.values()) if patient_id == current), 0)
        selected_label = st.selectbox("Patient auswählen", list(options), index=default_index)
        st.session_state.selected_patient = options[selected_label]
        selected_patient = next(
            patient for patient in patients if patient.id == options[selected_label]
        )
        try:
            current_birth_date = datetime.strptime(
                selected_patient.birth_date,
                "%Y-%m-%d",
            )
        except ValueError:
            current_birth_date = datetime(1980, 1, 1)
        with st.expander("Stammdaten bearbeiten"):
            with st.form("update_patient"):
                first, last = st.columns(2)
                updated_given = first.text_input("Vorname", value=selected_patient.given_name, max_chars=80)
                updated_family = last.text_input("Nachname", value=selected_patient.family_name, max_chars=80)
                gender_options = ["female", "male", "other", "unknown"]
                gender_index = gender_options.index(selected_patient.gender) if selected_patient.gender in gender_options else 3
                updated_gender = st.selectbox(
                    "Geschlecht",
                    gender_options,
                    index=gender_index,
                    format_func=lambda value: {"female": "Weiblich", "male": "Männlich", "other": "Divers", "unknown": "Nicht angegeben"}[value],
                )
                updated_birth_date = st.date_input(
                    "Geburtsdatum",
                    value=current_birth_date,
                    max_value=datetime.now(),
                )
                saved = st.form_submit_button("Stammdaten speichern", type="primary")
            if saved:
                if not updated_given.strip() or not updated_family.strip():
                    st.warning("Vor- und Nachname sind erforderlich.")
                elif api_call(lambda: client.update_patient(selected_patient.id, updated_given, updated_family, updated_gender, updated_birth_date.isoformat())):
                    st.success("Stammdaten aktualisiert.")
                    st.rerun()
        with st.expander("Patient löschen"):
            st.warning("Diese Aktion löscht den Patienten aus dem FHIR-Server.")
            with st.form("delete_patient"):
                confirm_delete = st.checkbox(
                    f"Löschen von {selected_patient.display_name or 'diesem Patienten'} bestätigen"
                )
                delete_submitted = st.form_submit_button(
                    "Patient endgültig löschen",
                    type="secondary",
                )
            if delete_submitted:
                if not confirm_delete:
                    st.warning("Bitte das Löschen bestätigen.")
                else:
                    try:
                        client.delete_patient(selected_patient.id)
                    except ApiError as exc:
                        st.error(str(exc))
                    else:
                        st.session_state.selected_patient = None
                        st.success("Patient wurde gelöscht.")
                        st.rerun()

elif page == "Observationen":
    st.markdown('<div class="eyebrow">Patientenverlauf</div><div class="hero"><h1>Vitalzeichen und Bericht</h1><p>Verlauf prüfen, neue Messwerte erfassen und die Patientenakte zusammenfassen.</p></div>', unsafe_allow_html=True)
    family, given, birthdate = st.columns(3)
    family_name = family.text_input("Nachname suchen", placeholder="z. B. Mustermann")
    given_name = given.text_input("Vorname suchen")
    birth_date = birthdate.text_input("Geburtsdatum", placeholder="JJJJ-MM-TT")
    patient_bundle = api_call(
        lambda: client.list_patients(family_name, given_name, birth_date)
    )
    patients = patients_from_bundle(patient_bundle or {})
    if not patients:
        st.info("Kein passender Patient gefunden.")
    else:
        options = {patient_label(patient): patient for patient in patients}
        selected_label = st.selectbox("Patient auswählen", list(options))
        patient = options[selected_label]
        bundle = api_call(lambda: client.list_observations(patient.id))
        resources = [entry["resource"] for entry in (bundle or {}).get("entry", []) if entry.get("resource")]
        show_observation_chart(resources)
        st.divider()
        with st.expander("Vitalzeichen hinzufügen", expanded=True):
            with st.form("create_patient_observation"):
                presets = {
                    "Herzfrequenz": ("8867-4", "/min"), "Körpertemperatur": ("8310-5", "Cel"),
                    "Atemfrequenz": ("9279-1", "/min"), "Sauerstoffsättigung": ("2708-6", "%"),
                    "Schmerzscore": ("72514-3", "score"), "Mobilitätsscore": ("83186-7", "score"),
                    "Morse-Sturzscore": ("59460-6", "score"), "Blutdruck": ("85354-9", "mmHg"),
                }
                display = st.selectbox("Vitalzeichen", list(presets))
                if display == "Blutdruck":
                    systolic, diastolic = st.columns(2)
                    systolic_value = systolic.number_input("Systolisch (mmHg)", min_value=0.0, step=1.0)
                    diastolic_value = diastolic.number_input("Diastolisch (mmHg)", min_value=0.0, step=1.0)
                else:
                    value = st.number_input("Wert", min_value=0.0, step=0.1)
                    st.caption(f"Einheit: {presets[display][1]}")
                effective = st.date_input("Datum", value=datetime.now()).isoformat() + "T09:00:00+00:00"
                saved = st.form_submit_button("Vitalzeichen speichern", type="primary")
            if saved:
                if display == "Blutdruck":
                    result = api_call(lambda: client.create_blood_pressure(patient.id, systolic_value, diastolic_value, effective))
                else:
                    code, unit = presets[display]
                    result = api_call(lambda: client.create_observation(patient.id, code, display, value, unit, effective))
                if result:
                    st.success("Vitalzeichen gespeichert.")
                    st.rerun()
        st.divider()
        show_patient_report(patient, resources)

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
                        presets = {
                            "Herzfrequenz": ("8867-4", "/min"),
                            "Körpertemperatur": ("8310-5", "Cel"),
                            "Atemfrequenz": ("9279-1", "/min"),
                            "Sauerstoffsättigung": ("2708-6", "%"),
                            "Schmerzscore": ("72514-3", "score"),
                            "Mobilitätsscore": ("83186-7", "score"),
                            "Morse-Sturzscore": ("59460-6", "score"),
                            "Blutdruck": ("85354-9", "mmHg"),
                        }
                        display = st.selectbox("Messgröße", list(presets))
                        if display == "Blutdruck":
                            systolic, diastolic = st.columns(2)
                            systolic_value = systolic.number_input("Systolisch (mmHg)", min_value=0.0, step=1.0)
                            diastolic_value = diastolic.number_input("Diastolisch (mmHg)", min_value=0.0, step=1.0)
                        else:
                            value = st.number_input("Wert", min_value=0.0, step=0.1)
                            st.caption(f"Einheit: {presets[display][1]}")
                        effective = st.date_input("Datum", value=datetime.now()).isoformat() + "T09:00:00+00:00"
                        save_observation = st.form_submit_button("Observation speichern", type="primary")
                    if save_observation:
                        if display == "Blutdruck":
                            result = api_call(lambda: client.create_blood_pressure(patient.id, systolic_value, diastolic_value, effective))
                        else:
                            code, unit = presets[display]
                            result = api_call(lambda: client.create_observation(patient.id, code, display, value, unit, effective))
                        if result:
                            st.success("Observation gespeichert.")
                            st.rerun()
            st.divider()
            st.subheader("Pflegeakte")
            diagnoses, medications, allergies, reports, care_plans = st.tabs([
                "Diagnosen",
                "Medikamente",
                "Allergien",
                "Pflegeberichte",
                "Pflegeplan",
            ])
            with diagnoses:
                clinical_record_panel(patient.id, "Condition", "Diagnose", ["active", "inactive", "resolved"], "Hinweise")
            with medications:
                clinical_record_panel(patient.id, "MedicationStatement", "Medikament", ["active", "completed", "stopped"], "Dosierung und Hinweise")
            with allergies:
                clinical_record_panel(patient.id, "AllergyIntolerance", "Allergen", ["active", "inactive", "resolved"], "Reaktion und Hinweise")
            with reports:
                clinical_record_panel(patient.id, "ClinicalImpression", "Titel des Pflegeberichts", ["completed"], "Pflegebericht")
            with care_plans:
                clinical_record_panel(patient.id, "CarePlan", "Pflegemaßnahme", ["active", "on-hold", "completed", "revoked"], "Ziel, Durchführung und Evaluation")
