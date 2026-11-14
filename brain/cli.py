import argparse
from pathlib import Path

import pandas as pd

from .agents import Brain
from .models import Asset, load_persona


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--persona", default="amira")
    p.add_argument("--request", default="")
    args = p.parse_args()
    root = Path(__file__).resolve().parents[1]
    assets = [
        Asset(**row)
        for row in pd.read_csv(root / "data/raw/assets_universe.csv").to_dict("records")
    ]
    d = Brain(assets).recommend(load_persona(args.persona, root), args.request)
    print(d.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
