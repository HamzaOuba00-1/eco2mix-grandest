"""Verifie qu'aucune variable ne contient d'information future."""
import numpy as np
import pandas as pd

from src.modele import construire_variables


def cadre_synthetique(heures: int = 1000) -> pd.DataFrame:
    index = pd.date_range("2020-01-01", periods=heures, freq="1h", tz="UTC")
    local = index.tz_convert("Europe/Paris")
    return pd.DataFrame({
        "y": np.arange(heures, dtype=float),     # strictement croissant
        "mois": local.month,
        "jour_semaine": local.dayofweek,
        "heure": local.hour,
    }, index=index)


def test_aucune_fuite_de_donnees():
    """Aucune variable ne doit depasser la valeur de y a T-24h.

    y vaut 0, 1, 2, ... donc toute variable construite correctement a
    l'instant T ne peut valoir plus que y[T-24].
    """
    cadre = construire_variables(cadre_synthetique())
    variables = [c for c in cadre.columns
                 if c.startswith(("lag_", "moy_", "min_", "max_"))]

    plafond = cadre["y"].shift(24)
    for variable in variables:
        if variable == "amplitude_24":
            continue                              # c'est un ecart, pas un niveau
        depassements = (cadre[variable] > plafond + 1e-9).sum()
        assert depassements == 0, (
            f"FUITE : '{variable}' contient de l'information future "
            f"({depassements} lignes)"
        )


def test_lag_24_est_bien_decale():
    cadre = construire_variables(cadre_synthetique())
    assert cadre["lag_24"].iloc[100] == cadre["y"].iloc[76]


def test_variables_calendaires():
    cadre = construire_variables(cadre_synthetique())
    assert set(cadre["weekend"].unique()) <= {0, 1}
    assert cadre["ferie"].sum() > 0                # 2020 a des jours feries
    assert cadre["heure_sin"].abs().max() <= 1.0
