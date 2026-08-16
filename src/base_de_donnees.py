"""Creation de la base DuckDB et chargement de l'historique.

Usage : python -m src.base_de_donnees
"""
from pathlib import Path

import duckdb

RACINE = Path(__file__).resolve().parents[1]
FICHIER_BASE = RACINE / "data" / "eco2mix.duckdb"
FICHIER_HISTORIQUE = RACINE / "data" / "historique_grand_est.parquet"

MESURES = [
    "consommation", "thermique", "nucleaire", "eolien",
    "solaire", "hydraulique", "pompage", "bioenergies", "ech_physiques",
]

COLONNES = ", ".join(["date_heure"] + MESURES + ["nature"])

SCHEMA = """
CREATE TABLE IF NOT EXISTS consommation (
    date_heure     TIMESTAMPTZ PRIMARY KEY,
    consommation   DOUBLE,
    thermique      DOUBLE,
    nucleaire      DOUBLE,
    eolien         DOUBLE,
    solaire        DOUBLE,
    hydraulique    DOUBLE,
    pompage        DOUBLE,
    bioenergies    DOUBLE,
    ech_physiques  DOUBLE,
    nature         VARCHAR,
    ingere_le      TIMESTAMPTZ DEFAULT now()
);
"""


def connexion() -> duckdb.DuckDBPyConnection:
    """Ouvre la base (la cree si absente) et garantit le schema."""
    FICHIER_BASE.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(FICHIER_BASE)
    con.execute(SCHEMA)
    con.execute("SET TimeZone = 'Europe/Paris';")
    return con


def charger_historique(con: duckdb.DuckDBPyConnection) -> int:
    """Insere le Parquet historique. Idempotent : les doublons sont ignores."""
    if not FICHIER_HISTORIQUE.exists():
        raise FileNotFoundError(
            f"{FICHIER_HISTORIQUE} absent. Lance d'abord : "
            "python -m src.ingest_historique"
        )

    avant = con.execute("SELECT count(*) FROM consommation").fetchone()[0]

    con.execute(f"""
        INSERT INTO consommation ({COLONNES})
        SELECT {COLONNES}
        FROM read_parquet('{FICHIER_HISTORIQUE}')
        ON CONFLICT (date_heure) DO NOTHING;
    """)

    apres = con.execute("SELECT count(*) FROM consommation").fetchone()[0]
    return apres - avant


if __name__ == "__main__":
    con = connexion()
    inserees = charger_historique(con)

    print(f"Lignes inserees : {inserees:,}")
    print(f"Total en base   : "
          f"{con.execute('SELECT count(*) FROM consommation').fetchone()[0]:,}")

    print("\n--- Etendue ---")
    print(con.execute("""
        SELECT min(date_heure)     AS debut,
               max(date_heure)     AS fin,
               count(*)            AS lignes,
               count(consommation) AS mesures_valides
        FROM consommation
    """).df().to_string(index=False))

    con.close()
