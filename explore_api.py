"""Script jetable : inspecter n'importe quel dataset ODRE.

Usage : python explore_api.py <nom_du_dataset>
"""
import sys
import requests

BASE = "https://odre.opendatasoft.com/api/explore/v2.1/catalog/datasets"


def inspecter(dataset: str, region: str = "Grand Est") -> None:
    reponse = requests.get(
        f"{BASE}/{dataset}/records",
        params={
            "where": f'libelle_region = "{region}"',
            "order_by": "date_heure desc",   # le plus récent d'abord
            "limit": 1,
        },
        timeout=30,
    )
    print(f"=== {dataset} === HTTP {reponse.status_code}")
    reponse.raise_for_status()

    data = reponse.json()
    print(f"Enregistrements pour '{region}' : {data['total_count']}\n")

    if not data["results"]:
        print("Aucun resultat — verifie le libelle de region.")
        return

    for cle, valeur in data["results"][0].items():
        print(f"  {cle:25} = {valeur}")


if __name__ == "__main__":
    dataset = sys.argv[1] if len(sys.argv) > 1 else "eco2mix-regional-tr"
    inspecter(dataset)
