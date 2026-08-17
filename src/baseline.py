"""Baselines de prevision a 24h.

Usage : python -m src.baseline
"""
import pandas as pd

from src.base_de_donnees import connexion

HORIZON = 24                    # heures d'avance
DEBUT_TEST = "2025-08-01"       # tout ce qui suit sert uniquement a evaluer


def charger() -> pd.DataFrame:
    """Serie horaire continue, indexee en UTC."""
    con = connexion()
    df = con.execute("""
        SELECT date_heure, consommation
        FROM consommation
        WHERE consommation IS NOT NULL
        ORDER BY date_heure
    """).df()
    con.close()

    serie = df.set_index("date_heure")["consommation"]
    serie.index = serie.index.tz_convert("UTC")

    # Reindexation sur une grille horaire parfaite : les trous deviennent NaN
    grille = pd.date_range(serie.index.min(), serie.index.max(),
                           freq="1h", tz="UTC")
    serie = serie.reindex(grille)
    print(f"Heures totales : {len(serie):,}  |  "
          f"trous : {serie.isna().sum():,}")

    cadre = pd.DataFrame({"y": serie})
    local = cadre.index.tz_convert("Europe/Paris")
    cadre["mois"] = local.month
    cadre["jour_semaine"] = local.dayofweek
    cadre["heure"] = local.hour
    return cadre


def evaluer(y_vrai: pd.Series, y_pred: pd.Series) -> dict:
    """MAE, RMSE, MAPE sur les points ou les deux series sont definies."""
    ok = y_vrai.notna() & y_pred.notna()
    vrai, pred = y_vrai[ok], y_pred[ok]
    erreur = vrai - pred
    return {
        "MAE (MW)": erreur.abs().mean(),
        "RMSE (MW)": (erreur ** 2).mean() ** 0.5,
        "MAPE (%)": (erreur.abs() / vrai).mean() * 100,
        "points": len(vrai),
    }


if __name__ == "__main__":
    cadre = charger()
    bascule = pd.Timestamp(DEBUT_TEST, tz="UTC")

    # --- Predicteurs disponibles a T pour prevoir T + 24h ---
    # decaler de 24h = "la valeur d'il y a 24h", connue au moment de predire
    cadre["j-1"] = cadre["y"].shift(HORIZON)        # meme heure hier
    cadre["j-7"] = cadre["y"].shift(24 * 7)         # meme heure il y a 7 jours
    cadre["mixte"] = (cadre["j-1"] + cadre["j-7"]) / 2

    train = cadre[cadre.index < bascule]
    test = cadre[cadre.index >= bascule].copy()

    print(f"\nApprentissage : {train.index.min().date()} -> "
          f"{train.index.max().date()}  ({len(train):,} h)")
    print(f"Test          : {test.index.min().date()} -> "
          f"{test.index.max().date()}  ({len(test):,} h)")

    # --- Climatologie : moyenne par (mois, jour, heure), calculee sur le train ---
    cle = ["mois", "jour_semaine", "heure"]
    profil = train.groupby(cle)["y"].mean().to_frame("climatologie")
    test = test.join(profil, on=cle)

    BASELINES = {
        "Persistance J-1  (meme heure hier)": "j-1",
        "Persistance J-7  (meme heure S-1)": "j-7",
        "Moyenne J-1 / J-7": "mixte",
        "Climatologie (mois x jour x heure)": "climatologie",
    }

    resultats = {
        nom: evaluer(test["y"], test[colonne])
        for nom, colonne in BASELINES.items()
    }

    print("\n--- RESULTATS SUR LA PERIODE DE TEST ---")
    tableau = pd.DataFrame(resultats).T
    print(tableau.round(2).to_string())

    meilleure = tableau["MAE (MW)"].idxmin()
    print(f"\nMeilleure baseline : {meilleure}")
    print(f"MAE a battre : {tableau.loc[meilleure, 'MAE (MW)']:.0f} MW "
          f"({tableau.loc[meilleure, 'MAPE (%)']:.2f} %)")
