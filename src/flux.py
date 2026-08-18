"""Flux Prefect d'ingestion horaire.

Local  : python -m src.flux
Deploie : python -m src.flux --deploy
"""
import sys
from datetime import timedelta

import pandas as pd
from prefect import flow, get_run_logger, task

from src.base_de_donnees import connexion
from src.ingest_temps_reel import (
    inserer,
    point_de_depart,
    telecharger,
    transformer,
)


@task(retries=3, retry_delay_seconds=[30, 120, 300], timeout_seconds=180)
def extraire(depuis: str) -> pd.DataFrame:
    """Appel a l'API RTE. Reessaye : le reseau est la partie fragile."""
    journal = get_run_logger()
    brut = telecharger(depuis)
    journal.info(f"{len(brut):,} lignes brutes recuperees depuis le {depuis}")
    return brut


@task
def nettoyer(brut: pd.DataFrame) -> pd.DataFrame:
    """Transformation pure : deterministe, donc aucun reessai utile."""
    journal = get_run_logger()
    propre = transformer(brut)
    journal.info(f"{len(propre):,} heures completes exploitables")
    return propre


@task(retries=2, retry_delay_seconds=10)
def charger(propre: pd.DataFrame) -> dict:
    """Ecriture en base. Reessaye : DuckDB peut etre verrouille."""
    journal = get_run_logger()
    con = connexion()
    try:
        nouvelles, majs = inserer(con, propre)
        total = con.execute("SELECT count(*) FROM consommation").fetchone()[0]
    finally:
        con.close()
    journal.info(f"{nouvelles:,} nouvelles, {majs:,} mises a jour "
                 f"(total : {total:,})")
    return {"nouvelles": nouvelles, "majs": majs, "total": total}


@task
def controler() -> dict:
    """Verification finale : les donnees sont-elles vraiment fraiches ?"""
    journal = get_run_logger()
    con = connexion()
    try:
        derniere = con.execute(
            "SELECT max(date_heure) FROM consommation "
            "WHERE consommation IS NOT NULL"
        ).fetchone()[0]
    finally:
        con.close()

    retard = (pd.Timestamp.now(tz="UTC") - derniere).total_seconds() / 3600
    if retard > 6:
        raise ValueError(
            f"Donnees obsoletes : derniere observation il y a {retard:.1f} h"
        )
    journal.info(f"Fraicheur OK : {retard:.1f} h de retard")
    return {"derniere": derniere.isoformat(), "retard_h": round(retard, 1)}


@flow(name="ingestion-eco2mix", log_prints=True)
def ingestion() -> dict:
    """Cycle complet : extraire, nettoyer, charger, controler."""
    con = connexion()
    depuis = point_de_depart(con)
    con.close()

    brut = extraire(depuis)
    propre = nettoyer(brut)
    resultat = charger(propre)
    resultat.update(controler())
    return resultat


if __name__ == "__main__":
    if "--deploy" in sys.argv:
        ingestion.serve(
            name="horaire",
            interval=timedelta(hours=1),
            tags=["eco2mix", "ingestion"],
        )
    else:
        print(ingestion())
