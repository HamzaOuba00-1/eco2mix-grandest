"""Backfill : telecharge l'historique consolide de consommation du Grand Est.

A lancer une seule fois : python -m src.ingest_historique
"""
from pathlib import Path

import pandas as pd
import requests

BASE_URL = "https://odre.opendatasoft.com/api/explore/v2.1/catalog/datasets"
DATASET = "eco2mix-regional-cons-def"
REGION = "Grand Est"

MESURES = [
    "consommation", "thermique", "nucleaire", "eolien",
    "solaire", "hydraulique", "pompage", "bioenergies", "ech_physiques",
]
COLONNES = ["date_heure"] + MESURES

RACINE = Path(__file__).resolve().parents[1]
FICHIER_BRUT = RACINE / "data" / "raw" / "historique_brut.json"
FICHIER_PROPRE = RACINE / "data" / "historique_grand_est.parquet"


def telecharger() -> Path:
    """Recupere l'historique complet via l'endpoint d'export."""
    FICHIER_BRUT.parent.mkdir(parents=True, exist_ok=True)

    if FICHIER_BRUT.exists():
        print(f"Fichier deja present ({FICHIER_BRUT.stat().st_size / 1e6:.1f} Mo).")
        print("Supprime-le pour retelecharger.")
        return FICHIER_BRUT

    params = {
        "select": ",".join(COLONNES),
        "where": f'libelle_region = "{REGION}"',
        "order_by": "date_heure",
        "timezone": "UTC",
    }

    print("Telechargement en cours (cela peut prendre quelques minutes)...")
    with requests.get(
        f"{BASE_URL}/{DATASET}/exports/json",
        params=params, stream=True, timeout=900,
    ) as reponse:
        reponse.raise_for_status()
        octets = 0
        with open(FICHIER_BRUT, "wb") as fichier:
            for morceau in reponse.iter_content(chunk_size=65536):
                fichier.write(morceau)
                octets += len(morceau)
                print(f"\r  {octets / 1e6:6.1f} Mo", end="", flush=True)
    print("\nTelechargement termine.")
    return FICHIER_BRUT


def transformer(chemin: Path) -> pd.DataFrame:
    """Nettoie, type et agrege la serie au pas horaire."""
    df = pd.read_json(chemin)
    print(f"\nLignes brutes             : {len(df):,}")

    # --- Diagnostic : quels types pandas a-t-il devines ? ---
    print("\nTypes devines par pandas :")
    for colonne in COLONNES:
        print(f"  {colonne:16} {df[colonne].dtype}")

    # --- Typage explicite : on ne fait pas confiance a l'inference ---
    df["date_heure"] = pd.to_datetime(df["date_heure"], utc=True)

    print("\nConversion numerique forcee :")
    for colonne in MESURES:
        avant = df[colonne].isna().sum()
        df[colonne] = pd.to_numeric(df[colonne], errors="coerce")
        apres = df[colonne].isna().sum()
        if apres > avant:
            print(f"  {colonne:16} {apres - avant:,} valeurs illisibles -> NaN")

    df = df.sort_values("date_heure")

    avant = len(df)
    df = df.drop_duplicates(subset="date_heure", keep="last")
    print(f"\nDoublons supprimes        : {avant - len(df):,}")

    horaire = (
        df.set_index("date_heure")[MESURES]
        .resample("1h")
        .mean()
        .round(2)
    )
    horaire["nature"] = "historique"
    print(f"Lignes apres agregation   : {len(horaire):,}")
    return horaire.reset_index()


def verifier(df: pd.DataFrame) -> None:
    """Controles qualite : periode, trous, valeurs manquantes."""
    print("\n--- CONTROLES QUALITE ---")
    debut, fin = df["date_heure"].min(), df["date_heure"].max()
    print(f"Periode couverte : {debut}  ->  {fin}")

    attendu = int((fin - debut).total_seconds() // 3600) + 1
    print(f"Heures attendues : {attendu:,}   |   presentes : {len(df):,}")

    manquants = df["consommation"].isna().sum()
    print(f"Consommation manquante : {manquants:,} ({manquants / len(df):.2%})")
    print(f"\nConsommation (MW) :\n{df['consommation'].describe().round(0)}")


if __name__ == "__main__":
    brut = telecharger()
    propre = transformer(brut)
    verifier(propre)

    propre.to_parquet(FICHIER_PROPRE, index=False)
    taille = FICHIER_PROPRE.stat().st_size / 1e6
    print(f"\nEcrit : {FICHIER_PROPRE.name}  ({taille:.1f} Mo)")
