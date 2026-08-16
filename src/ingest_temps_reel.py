"""Ingestion incrementale depuis le dataset temps reel.

Usage : python -m src.ingest_temps_reel
"""
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests

from src.base_de_donnees import COLONNES, MESURES, connexion

URL = ("https://odre.opendatasoft.com/api/explore/v2.1"
       "/catalog/datasets/eco2mix-regional-tr/records")
REGION = "Grand Est"
JOURS_RECOUVREMENT = 2
TAILLE_PAGE = 100


def point_de_depart(con) -> str:
    dernier = con.execute(
        "SELECT max(date_heure) FROM consommation WHERE consommation IS NOT NULL"
    ).fetchone()[0]
    if dernier is None:
        depart = datetime.now(timezone.utc) - timedelta(days=60)
    else:
        depart = dernier - timedelta(days=JOURS_RECOUVREMENT)
    return depart.strftime("%Y-%m-%d")


def telecharger(depuis: str) -> pd.DataFrame:
    where = f'libelle_region = "{REGION}" and date_heure >= date\'{depuis}\''
    lignes, offset, attendu = [], 0, None

    while True:
        reponse = requests.get(URL, timeout=60, params={
            "select": ",".join(["date_heure"] + MESURES),
            "where": where,
            "order_by": "date_heure",
            "limit": TAILLE_PAGE,
            "offset": offset,
            "timezone": "UTC",
        })
        reponse.raise_for_status()
        data = reponse.json()
        page = data.get("results", [])

        if attendu is None:
            attendu = data.get("total_count", 0)
            print(f"  L'API annonce {attendu:,} lignes")
            # GARDE-FOU : des lignes annoncees mais rien renvoye = anomalie
            if attendu > 0 and not page:
                raise RuntimeError(
                    f"L'API annonce {attendu} lignes mais renvoie une page vide. "
                    f"URL : {reponse.url}"
                )

        if not page:
            break

        lignes.extend(page)
        offset += TAILLE_PAGE
        print(f"\r  {len(lignes):,} / {attendu:,} lignes", end="", flush=True)

        if offset >= attendu or offset >= 9_000:
            break

    print()
    return pd.DataFrame(lignes)


def transformer(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    df["date_heure"] = pd.to_datetime(df["date_heure"], utc=True)
    for colonne in MESURES:
        df[colonne] = pd.to_numeric(df[colonne], errors="coerce")

    df = df.sort_values("date_heure").drop_duplicates("date_heure", keep="last")
    horaire = df.set_index("date_heure")[MESURES].resample("1h").mean().round(2)

    maintenant = pd.Timestamp.now(tz="UTC")
    horaire = horaire[horaire.index + pd.Timedelta(hours=1) <= maintenant]
    horaire = horaire[horaire["consommation"].notna()]
    horaire["nature"] = "temps_reel"
    return horaire.reset_index()


DTYPES_TEXTE = {"str", "string", "string[python]", "string[pyarrow]"}


def compatibiliser(df: pd.DataFrame) -> pd.DataFrame:
    """Ramene les colonnes texte en dtype 'object', seul format lu par DuckDB.

    pandas 3.0 utilise un dtype 'str' adosse a PyArrow que DuckDB 1.4
    ne reconnait pas encore.
    """
    df = df.copy()
    for colonne in df.columns:
        if str(df[colonne].dtype) in DTYPES_TEXTE:
            df[colonne] = df[colonne].astype(object)
    return df


def inserer(con, df: pd.DataFrame) -> tuple[int, int]:
    if df.empty:
        return 0, 0
    df = compatibiliser(df)
    avant = con.execute("SELECT count(*) FROM consommation").fetchone()[0]
    maj = ", ".join(f"{c} = excluded.{c}" for c in MESURES + ["nature"])

    con.register("nouvelles", df)
    con.execute(f"""
        INSERT INTO consommation ({COLONNES})
        SELECT {COLONNES} FROM nouvelles
        ON CONFLICT (date_heure) DO UPDATE SET {maj}, ingere_le = now();
    """)
    con.unregister("nouvelles")

    apres = con.execute("SELECT count(*) FROM consommation").fetchone()[0]
    return apres - avant, len(df) - (apres - avant)


if __name__ == "__main__":
    con = connexion()
    depuis = point_de_depart(con)
    print(f"Interrogation de l'API depuis le {depuis}")

    brut = telecharger(depuis)
    print(f"Lignes brutes recuperees : {len(brut):,}")

    propre = transformer(brut)
    print(f"Heures completes exploitables : {len(propre):,}")

    nouvelles, majs = inserer(con, propre)
    print(f"  nouvelles : {nouvelles:,}   |   mises a jour : {majs:,}")

    print("\n--- Etat de la base ---")
    print(con.execute("""
        SELECT nature, count(*) AS lignes,
               min(date_heure) AS debut, max(date_heure) AS fin
        FROM consommation GROUP BY nature ORDER BY debut
    """).df().to_string(index=False))
    con.close()
