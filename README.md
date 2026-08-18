# ⚡ Prévision de la consommation électrique — Grand Est

![CI](https://github.com/HamzaOuba00-1/eco2mix-grandest/actions/workflows/ci.yml/badge.svg)

Pipeline MLOps de bout en bout sur les données ouvertes éCO2mix (RTE) :
ingestion orchestrée, stockage analytique, modèle de prévision, API et dashboard.
Le tout conteneurisé, testé et intégré en continu.

> Prévision de la consommation électrique régionale à 24 h, avec une erreur
> moyenne de **162 MW (3,4 %)** — soit **33 % de mieux** qu'une baseline de
> persistance, sur une année de test hors échantillon.

![Dashboard](docs/dashboard.png)

## Architecture

API RTE → **Prefect** (flow horaire, retries, contrôle qualité) → **DuckDB**
(119 000 h, 2013 → aujourd'hui) → **modèle GBM** → **FastAPI** → **Streamlit**.

| Service | URL |
|---|---|
| API (docs interactives) | http://localhost:8000/docs |
| Dashboard | http://localhost:8501 |
| Prefect | http://localhost:4200 |

## Démarrage

    git clone git@github.com:HamzaOuba00-1/eco2mix-grandest.git
    cd eco2mix-grandest
    python -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt

    python -m src.ingest_historique    # backfill 2013 -> M-1
    python -m src.base_de_donnees      # creation DuckDB
    python -m src.ingest_temps_reel    # donnees recentes
    python -m src.modele               # entrainement

    docker compose up -d

## Données

Deux sources complémentaires, imposées par le cycle de vie des données RTE :

| Source | Rôle | Pas | Couverture |
|---|---|---|---|
| `eco2mix-regional-cons-def` | backfill unique | 30 min | 2013 → M-1 |
| `eco2mix-regional-tr` | ingestion horaire | 15 min | ~45 jours glissants |

Le dataset temps réel étant **effacé chaque mois**, l'ingestion continue est ce
qui permet de conserver l'historique. Les deux sources sont normalisées au pas
horaire, en UTC, dans une table unique avec traçabilité de l'origine.

## Modèle

`HistGradientBoostingRegressor`, 22 variables : décalages (24 h à 336 h),
agrégats glissants, calendrier (heure, jour, mois, jours fériés) avec encodage
cyclique. Découpage temporel strict, sans mélange aléatoire.

| Modèle | MAE | RMSE | MAPE |
|---|---|---|---|
| Persistance J-1 | 275 MW | 384 MW | 5,88 % |
| Persistance J-7 | 330 MW | 457 MW | 6,70 % |
| Climatologie | 347 MW | 443 MW | 7,34 % |
| Moyenne J-1/J-7 (baseline) | 243 MW | 325 MW | 5,04 % |
| **Gradient boosting** | **162 MW** | **215 MW** | **3,36 %** |

Période de test : 2025-08 → 2026-08 (9 133 heures jamais vues à l'entraînement).

## Limites identifiées

**Pas de données météo.** `lag_24` domine largement l'importance des variables :
il sert de proxy à la température. Conséquence mesurée — l'erreur double en
hiver (222 MW en janvier contre 102 MW en août), période où la thermosensibilité
est maximale et où la prévision a le plus de valeur. L'intégration de
Météo-France est l'axe d'amélioration prioritaire.

**DuckDB mono-écrivain.** Adapté ici (un seul processus écrit), à remplacer par
PostgreSQL en cas d'écritures concurrentes.

**Pas de validation croisée temporelle** ni de réentraînement automatique.

## Qualité

- 9 tests unitaires, dont un test de **non-fuite de données** vérifiant
  qu'aucune variable ne contient d'information future
- CI GitHub Actions : ruff, pytest, build Docker
- `DeprecationWarning` traités comme des erreurs
- Ingestion **idempotente** (clé primaire + UPSERT), rejouable sans effet de bord
- Endpoint `/health` contrôlant la **fraîcheur des données**, pas seulement la
  disponibilité du service

## Structure

    src/
    ├── ingest_historique.py   backfill via l'endpoint d'export
    ├── ingest_temps_reel.py   ingestion incrementale (watermark + recouvrement)
    ├── base_de_donnees.py     schema DuckDB et connexion
    ├── baseline.py            baselines de reference
    ├── modele.py              variables et entrainement
    ├── api.py                 FastAPI
    ├── dashboard.py           Streamlit
    └── flux.py                flow Prefect

## Source des données

[ODRÉ — Open Data Réseaux Énergies](https://odre.opendatasoft.com), RTE.
Licence Ouverte / Open Licence.
