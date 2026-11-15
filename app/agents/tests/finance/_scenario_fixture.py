"""Table de scénarios FICTIVE pour les tests de PROB_LOSS et de l'explicabilité des scénarios.

TOUTES LES VALEURS SONT INVENTÉES (FICTIF_*) : elles ne viennent d'aucun modèle ni d'aucune donnée réelle et ne
servent qu'à vérifier la mécanique (comparaison à α, horizon hors grille, paliers, désaccord entre modèles).
"""

from __future__ import annotations

from alphaforge.scenarios.tool_table import LATEST_KEY, build_manifest, dumps_table

RUN_ID = "fixture-prob-loss"
CODE_SHA = "fictif01"
DATA_SHA = {"CAD77": "f" * 64}
MIX = "ca15-us25-bd45-cs10-gd05"
# Poids de l'engine qui tombent exactement sur MIX (rattachement prudent par défaut, CAD77).
WEIGHTS = {"XIU.TO": 0.15, "SPY": 0.25, "XBB.TO": 0.45, "ZST.TO": 0.10, "GLD": 0.05}

# (modèle, horizon, métrique) -> (valeur, ci_lo, ci_hi) : FICTIF.
VALUES = {
    ("FICTIF_a", 1, "p_loss_gt_05"): (0.10, 0.07, 0.13),
    ("FICTIF_a", 1, "p_loss_gt_10"): (0.05, 0.03, 0.07),
    ("FICTIF_a", 1, "p_loss_gt_20"): (0.01, 0.00, 0.02),
    ("FICTIF_a", 3, "p_loss_gt_05"): (0.08, 0.05, 0.11),
    ("FICTIF_a", 3, "p_loss_gt_10"): (0.04, 0.02, 0.06),
    ("FICTIF_a", 3, "p_loss_gt_20"): (0.01, 0.00, 0.02),
    ("FICTIF_a", 5, "p_loss_gt_05"): (0.06, 0.03, 0.10),
    ("FICTIF_a", 5, "p_loss_gt_10"): (0.03, 0.01, 0.08),
    ("FICTIF_a", 5, "p_loss_gt_20"): (0.01, 0.00, 0.03),
    ("FICTIF_a", 3, "ret_ann_p50"): (0.05, 0.03, 0.07),
    ("FICTIF_b", 1, "p_loss_gt_10"): (0.06, 0.04, 0.09),
    ("FICTIF_b", 3, "p_loss_gt_10"): (0.07, 0.05, 0.12),
    ("FICTIF_b", 5, "p_loss_gt_10"): (0.05, 0.02, 0.09),
}


def rows() -> list[dict]:
    out = []
    for (model, h, metric), (v, lo, hi) in VALUES.items():
        out.append(
            {
                "schema_version": "0.2",
                "model_id": model,
                "family": "CAD77",
                "currency": "CAD",
                "mix_id": MIX,
                "horizon_years": h,
                "basis": "nominal",
                "metric": metric,
                "value": v,
                "ci_lo": lo,
                "ci_hi": hi,
                "n_paths": 1000,
                "n_boot": 20,
                "seed": 7,
                "fitted_through": "2026-09",
                "window_start": "1977-01",
                "n_hist_months": 597,
                "hypothese": False,
                "data_sha256": DATA_SHA["CAD77"],
                "code_sha": CODE_SHA,
            }
        )
    return out


def publish(store) -> None:
    body = dumps_table(rows())
    manifest = build_manifest(
        RUN_ID,
        body,
        code_sha=CODE_SHA,
        data_sha256=DATA_SHA,
        default_model="FICTIF_a",
        models=[
            {"model_id": "FICTIF_a", "name": "modèle fictif A", "display": "default"},
            {"model_id": "FICTIF_b", "name": "modèle fictif B", "display": "compare"},
        ],
    )
    prefix = f"scenarios/output/{RUN_ID}/"
    store.put(prefix + "table.csv", body, content_type="text/csv")
    store.put_json(prefix + "manifest.json", manifest)
    store.put_json(LATEST_KEY, {"run_id": RUN_ID})


def fid(model: str, h: int, metric: str, suffix: str = "") -> str:
    return f"scn.{model}.CAD77.{MIX}.{h}y.nominal.{metric}" + (f".{suffix}" if suffix else "")


class DeniedS3:
    """Client S3 factice : GetObject et ListObjectsV2 refusés (AccessDenied, 403), comme un rôle sans droit."""

    def _deny(self, op):
        from botocore.exceptions import ClientError

        raise ClientError(
            {
                "Error": {"Code": "AccessDenied", "Message": "Access Denied"},
                "ResponseMetadata": {"HTTPStatusCode": 403},
            },
            op,
        )

    def get_object(self, Bucket, Key):
        self._deny("GetObject")

    def head_object(self, Bucket, Key):
        self._deny("HeadObject")

    def list_objects_v2(self, Bucket, Prefix, MaxKeys):
        self._deny("ListObjectsV2")
