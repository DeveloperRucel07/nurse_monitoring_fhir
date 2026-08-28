import streamlit as st


def risk_color(status: str) -> str:
    normalized = status.lower()
    if normalized in {"high", "hoch", "positive"}:
        return "#c2413b"
    if normalized in {"medium", "mittel", "moderate"}:
        return "#c47b20"
    if normalized in {"low", "niedrig", "negative"}:
        return "#2f7d68"
    return "#64748b"


def risk_card(label: str, probability: float | None, status: str, missing: str) -> None:
    probability_text = f"{probability:.0%}" if probability is not None else "n. a."
    color = risk_color(status)
    missing_text = f"Fehlende Werte: {missing}" if missing else "Alle verfügbaren Merkmale berücksichtigt"
    st.markdown(
        f'<div class="risk-card"><div class="risk-heading"><span>{label}</span><strong style="color:{color}">{probability_text}</strong></div><div class="risk-bar"><span style="width:{min(max((probability or 0) * 100, 0), 100):.0f}%;background:{color}"></span></div><div class="risk-meta"><span style="color:{color}">{status}</span><span>{missing_text}</span></div></div>',
        unsafe_allow_html=True,
    )
