"""Dashboard de prevision de consommation electrique du Grand Est.

Lancement : streamlit run src/dashboard.py
"""
import os

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

API = os.getenv("API_URL", "http://localhost:8000")
FUSEAU = "Europe/Paris"

st.set_page_config(page_title="Consommation Grand Est", page_icon="⚡",
                   layout="wide")


@st.cache_data(ttl=300)
def appeler(route: str, **params) -> dict | list:
    reponse = requests.get(f"{API}{route}", params=params, timeout=30)
    reponse.raise_for_status()
    return reponse.json()


def en_cadre(points: list) -> pd.DataFrame:
    df = pd.DataFrame(points)
    df["date_heure"] = pd.to_datetime(df["date_heure"]).dt.tz_convert(FUSEAU)
    return df


st.title("⚡ Consommation électrique — Grand Est")
st.caption("Données éCO2mix (RTE) · prévision à 24 h par gradient boosting")

# --- Etat du service ---
try:
    sante = appeler("/health")
except Exception as erreur:
    st.error(f"API injoignable sur {API} — le service est-il démarré ? ({erreur})")
    st.stop()

if sante["statut"] != "ok":
    st.warning(
        f"⚠️ Données obsolètes : dernière observation il y a "
        f"{sante['retard_heures']} h. Relancer l'ingestion."
    )

jours = st.sidebar.slider("Historique affiché (jours)", 1, 30, 7)
if st.sidebar.button("Rafraîchir"):
    st.cache_data.clear()
    st.rerun()

historique = en_cadre(appeler("/historique", heures=jours * 24))
prevision = en_cadre(appeler("/predictions")["points"])

# --- Indicateurs ---
actuelle = historique["consommation_mw"].iloc[-1]
pointe = prevision["consommation_mw"].max()
heure_pointe = prevision.loc[prevision["consommation_mw"].idxmax(), "date_heure"]

colonnes = st.columns(4)
colonnes[0].metric("Dernière mesure", f"{actuelle:,.0f} MW")
colonnes[1].metric("Pointe prévue", f"{pointe:,.0f} MW",
                   f"{pointe - actuelle:+,.0f} MW")
colonnes[2].metric("Heure de pointe", heure_pointe.strftime("%d/%m %Hh"))
colonnes[3].metric("Fraîcheur", f"{sante['retard_heures']:.1f} h")

# --- Graphique ---
figure = go.Figure()
figure.add_trace(go.Scatter(
    x=historique["date_heure"], y=historique["consommation_mw"],
    name="Observé", line=dict(color="#1f77b4", width=2),
))

# Relier la derniere observation a la premiere prevision
pont = pd.concat([historique.tail(1), prevision])
figure.add_trace(go.Scatter(
    x=pont["date_heure"], y=pont["consommation_mw"],
    name="Prévision 24 h", line=dict(color="#ff7f0e", width=2, dash="dash"),
))
# Plotly ne sait pas positionner une annotation sur une vline datetime
# (il calcule une moyenne arithmetique sur les dates). On dessine la ligne
# seule ; la legende suffit a distinguer observe et prevu.
maintenant = historique["date_heure"].iloc[-1].to_pydatetime()
figure.add_vline(x=maintenant, line_dash="dot", line_color="grey")
figure.update_layout(
    height=480, hovermode="x unified",
    yaxis_title="Consommation (MW)", xaxis_title=None,
    legend=dict(orientation="h", y=1.1),
    margin=dict(t=40, b=20),
)
st.plotly_chart(figure, use_container_width=True)

# --- Detail ---
with st.expander("Détail des prévisions"):
    affichage = prevision.copy()
    affichage["date_heure"] = affichage["date_heure"].dt.strftime("%d/%m %Hh")
    st.dataframe(
        affichage.rename(columns={"date_heure": "Heure",
                                  "consommation_mw": "Prévision (MW)"}),
        use_container_width=True, hide_index=True,
    )
