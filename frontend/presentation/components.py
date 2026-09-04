from html import escape

import streamlit as st


def risk_color(status: str) -> str:
    normalized = status.lower()
    if normalized == "incomplete-data":
        return "#c47b20"
    return "#4f6f7a"


def risk_card(label: str, probability: float | None, status: str, missing: str) -> None:
    probability_text = (
        f"Demo {probability:.0%}" if probability is not None else "unvollständig"
    )
    color = risk_color(status)
    missing_text = (
        f"Fehlende Werte: {missing}"
        if missing
        else "Synthetischer Modellwert – keine klinische Wahrscheinlichkeit"
    )
    status_text = (
        "Daten unvollständig"
        if status == "incomplete-data"
        else "Nicht klinisch validiert"
    )
    st.markdown(
        f'<div class="risk-card"><div class="risk-heading"><span>{escape(label)}</span><strong style="color:{color}">{probability_text}</strong></div><div class="risk-bar"><span style="width:{min(max((probability or 0) * 100, 0), 100):.0f}%;background:{color}"></span></div><div class="risk-meta"><span style="color:{color}">{escape(status_text)}</span><span>{escape(missing_text)}</span></div></div>',
        unsafe_allow_html=True,
    )
