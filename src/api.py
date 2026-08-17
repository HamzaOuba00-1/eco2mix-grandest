"""API de prevision de consommation electrique du Grand Est.

Lancement : uvicorn src.api:app --reload
"""
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

import joblib
import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from src.baseline import HORIZON, charger
from src.modele import FICHIER_MODELE, construire_variables

ETAT: dict = {}


class Point(BaseModel):
    date_heure: datetime
    consommation_mw: float


class Prevision(BaseModel):
    genere_le: datetime
    derniere_observation: datetime
    horizon_heures: int
    points: list[Point]


@asynccontextmanager
async def cycle_de_vie(app: FastAPI):
    """Charge le modele une seule fois, au demarrage."""
    if not Path(FICHIER_MODELE).exists():
        raise RuntimeError(
            f"{FICHIER_MODELE} absent. Lance d'abord : python -m src.modele"
        )
    ETAT.update(joblib.load(FICHIER_MODELE))
    print(f"Modele charge ({len(ETAT['variables'])} variables)")
    yield
    ETAT.clear()


app = FastAPI(
    title="Prevision consommation electrique - Grand Est",
    description="Prevision horaire a 24h a partir des donnees eCO2mix (RTE).",
    version="1.0.0",
    lifespan=cycle_de_vie,
)


def serie_actuelle() -> pd.DataFrame:
    """Serie horaire complete, rechargee a chaque appel."""
    cadre = charger()
    return cadre[cadre["y"].notna()]


@app.get("/health")
def sante() -> dict:
    """Verifie que le service et ses donnees sont operationnels."""
    try:
        cadre = serie_actuelle()
        derniere = cadre.index.max()
        retard = (pd.Timestamp.now(tz="UTC") - derniere).total_seconds() / 3600
        return {
            "statut": "ok" if retard < 6 else "donnees_obsoletes",
            "modele_charge": bool(ETAT),
            "derniere_observation": derniere.isoformat(),
            "retard_heures": round(retard, 1),
            "lignes_en_base": len(cadre),
        }
    except Exception as erreur:
        raise HTTPException(503, f"Service indisponible : {erreur}")


@app.get("/predictions", response_model=Prevision)
def predictions() -> Prevision:
    """Prevision des 24 prochaines heures."""
    if not ETAT:
        raise HTTPException(503, "Modele non charge")

    cadre = serie_actuelle()
    derniere = cadre.index.max()

    # Prolonger l'index de 24h avec des valeurs inconnues
    futur = pd.date_range(
        derniere + pd.Timedelta(hours=1), periods=HORIZON, freq="1h", tz="UTC"
    )
    etendu = cadre.reindex(cadre.index.union(futur))

    local = etendu.index.tz_convert("Europe/Paris")
    etendu["mois"] = local.month
    etendu["jour_semaine"] = local.dayofweek
    etendu["heure"] = local.hour

    variables = construire_variables(etendu).loc[futur, ETAT["variables"]]
    valeurs = ETAT["modele"].predict(variables)

    return Prevision(
        genere_le=datetime.now(timezone.utc),
        derniere_observation=derniere,
        horizon_heures=HORIZON,
        points=[
            Point(date_heure=horodatage, consommation_mw=round(float(valeur), 1))
            for horodatage, valeur in zip(futur, valeurs)
        ],
    )


@app.get("/historique", response_model=list[Point])
def historique(
    heures: int = Query(168, ge=1, le=8760, description="Nombre d'heures"),
) -> list[Point]:
    """Dernieres heures observees."""
    cadre = serie_actuelle().tail(heures)
    return [
        Point(date_heure=horodatage, consommation_mw=float(valeur))
        for horodatage, valeur in cadre["y"].items()
    ]
