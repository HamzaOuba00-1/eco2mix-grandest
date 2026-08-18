"""Tests de la logique de transformation des donnees."""
import pandas as pd

from src.ingest_temps_reel import transformer


def fabriquer(debut: str, heures: int, valeur=1000) -> pd.DataFrame:
    """Donnees synthetiques au pas 15 min, comme l'API temps reel."""
    index = pd.date_range(debut, periods=heures * 4, freq="15min", tz="UTC")
    lignes = {"date_heure": index.astype(str), "consommation": valeur}
    for colonne in ["thermique", "nucleaire", "eolien", "solaire",
                    "hydraulique", "pompage", "bioenergies", "ech_physiques"]:
        lignes[colonne] = 0
    return pd.DataFrame(lignes)


def test_agregation_horaire():
    """4 mesures de 15 min doivent produire 1 ligne horaire."""
    brut = fabriquer("2020-01-01", heures=5)
    propre = transformer(brut)
    assert len(propre) == 5
    assert propre["consommation"].iloc[0] == 1000


def test_moyenne_et_non_somme():
    """L'agregation d'une puissance est une moyenne, pas une somme."""
    brut = fabriquer("2020-01-01", heures=1)
    brut["consommation"] = [1000, 2000, 3000, 4000]
    propre = transformer(brut)
    assert propre["consommation"].iloc[0] == 2500   # et non 10000


def test_valeurs_texte_converties():
    """Une valeur textuelle ne doit pas casser la colonne (bug 'eolien')."""
    brut = fabriquer("2020-01-01", heures=1)
    brut["eolien"] = ["100", "100", "100", "abc"]
    propre = transformer(brut)
    assert propre["eolien"].iloc[0] == 100          # 'abc' -> NaN, ignore


def test_heures_incompletes_exclues():
    """Une heure non terminee ne doit jamais entrer en base."""
    futur = pd.Timestamp.now(tz="UTC") + pd.offsets.Hour(3)
    brut = fabriquer(futur.floor("h").isoformat(), heures=2)
    propre = transformer(brut)
    assert propre.empty


def test_consommation_nulle_exclue():
    """Les lignes pre-creees sans mesure sont ecartees."""
    brut = fabriquer("2020-01-01", heures=2)
    brut.loc[4:7, "consommation"] = None
    propre = transformer(brut)
    assert len(propre) == 1


def test_dataframe_vide():
    """Un DataFrame vide ne doit pas provoquer d'exception."""
    assert transformer(pd.DataFrame()).empty
