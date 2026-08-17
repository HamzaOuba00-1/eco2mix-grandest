"""Entrainement du modele de prevision a 24h.

Usage : python -m src.modele
"""
from pathlib import Path

import holidays
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.inspection import permutation_importance

from src.baseline import DEBUT_TEST, HORIZON, charger, evaluer

RACINE = Path(__file__).resolve().parents[1]
FICHIER_MODELE = RACINE / "models" / "modele.joblib"

DECALAGES = [24, 25, 26, 48, 72, 168, 336]
FENETRES = [24, 168]


def construire_variables(cadre: pd.DataFrame) -> pd.DataFrame:
    """Variables toutes disponibles a l'instant T pour prevoir T+24h."""
    df = cadre.copy()

    for decalage in DECALAGES:
        df[f"lag_{decalage}"] = df["y"].shift(decalage)

    base = df["y"].shift(HORIZON)          # rien de plus recent que T-24h
    for fenetre in FENETRES:
        df[f"moy_{fenetre}"] = base.rolling(fenetre).mean()
    df["min_24"] = base.rolling(24).min()
    df["max_24"] = base.rolling(24).max()
    df["amplitude_24"] = df["max_24"] - df["min_24"]

    local = df.index.tz_convert("Europe/Paris")
    df["jour_annee"] = local.dayofyear
    df["weekend"] = (df["jour_semaine"] >= 5).astype(int)

    feries = set(holidays.France(years=range(2012, 2028)).keys())
    df["ferie"] = pd.Index(local.date).isin(feries).astype(int)

    # Encodage cyclique : 23h et 0h doivent etre proches
    df["heure_sin"] = np.sin(2 * np.pi * df["heure"] / 24)
    df["heure_cos"] = np.cos(2 * np.pi * df["heure"] / 24)
    df["an_sin"] = np.sin(2 * np.pi * df["jour_annee"] / 365.25)
    df["an_cos"] = np.cos(2 * np.pi * df["jour_annee"] / 365.25)

    return df


if __name__ == "__main__":
    cadre = construire_variables(charger())
    variables = [c for c in cadre.columns if c != "y"]

    bascule = pd.Timestamp(DEBUT_TEST, tz="UTC")
    entrainement = cadre[(cadre.index < bascule) & cadre["y"].notna()]
    test = cadre[(cadre.index >= bascule) & cadre["y"].notna()]

    print(f"Variables     : {len(variables)}")
    print(f"Entrainement  : {len(entrainement):,} h  "
          f"({entrainement.index.min().date()} -> {entrainement.index.max().date()})")
    print(f"Test          : {len(test):,} h  "
          f"({test.index.min().date()} -> {test.index.max().date()})")

    modele = HistGradientBoostingRegressor(
        max_iter=500,
        learning_rate=0.05,
        max_leaf_nodes=63,
        min_samples_leaf=40,
        l2_regularization=1.0,
        early_stopping=False,
        random_state=42,
    )

    print("\nEntrainement en cours...")
    modele.fit(entrainement[variables], entrainement["y"])

    prediction = pd.Series(
        modele.predict(test[variables]), index=test.index
    )

    print("\n--- COMPARAISON SUR LA PERIODE DE TEST ---")
    comparaison = pd.DataFrame({
        "Baseline J-1/J-7": evaluer(test["y"], (test["lag_24"] + test["lag_168"]) / 2),
        "Gradient boosting": evaluer(test["y"], prediction),
    }).T
    print(comparaison.round(2).to_string())

    reference = comparaison.loc["Baseline J-1/J-7", "MAE (MW)"]
    obtenu = comparaison.loc["Gradient boosting", "MAE (MW)"]
    print(f"\nGain sur la MAE : {(1 - obtenu / reference):.1%}")

    print("\n--- IMPORTANCE DES VARIABLES (top 12) ---")
    importance = permutation_importance(
        modele, test[variables], test["y"],
        n_repeats=3, random_state=42, scoring="neg_mean_absolute_error",
    )
    classement = (
        pd.Series(importance.importances_mean, index=variables)
        .sort_values(ascending=False)
        .head(12)
    )
    print(classement.round(1).to_string())

    print("\n--- ERREUR PAR SAISON (MAE, MW) ---")
    saison = pd.DataFrame({"vrai": test["y"], "pred": prediction})
    saison["mois"] = saison.index.tz_convert("Europe/Paris").month
    print((saison["vrai"] - saison["pred"]).abs()
          .groupby(saison["mois"]).mean().round(0).to_string())

    FICHIER_MODELE.parent.mkdir(exist_ok=True)
    joblib.dump({"modele": modele, "variables": variables}, FICHIER_MODELE)
    print(f"\nModele enregistre : {FICHIER_MODELE.name}")
