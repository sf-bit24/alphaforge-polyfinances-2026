"""Répartition de l'argent d'une décision : par classe d'actifs, par devise de cotation et par secteur.

Calcul déterministe du moteur (l'interface n'en fait aucun) à partir des positions FINALES de la décision (poids
normalisés, somme 1). Chaque part devient un Fact cité (``mix.class.<clé>``, ``mix.currency.<clé>``,
``mix.sector.<clé>``, ``mix.amount.<actif>``, ``mix.amount_total``) : tout chiffre affiché est traçable.

Sources :
- classe, devise, secteur d'un titre : univers de marché (``alphaforge.market.universe``), dont les 31 actifs du jeu
  de départ (``starter:assets_universe.csv``) ; un actif ajouté hors jeu de départ est sourcé à
  ``data/market/universe.yaml`` ;
- montant de base : ``profile.investable_wealth`` (CAD) ; sans lui, les montants valent ``None`` ;
- secteurs des FNB d'actions : transparence (look-through) du moteur, ``lookthrough_us_mkt.parquet`` (part de chaque
  industrie Kenneth R. French dans la capitalisation américaine, au mois de ``as_of`` au plus tard). Seuls les FNB que
  le moteur fait suivre au marché américain (``proxy_for_ticker == "US_MKT"`` dans ``assets.csv`` : SPY, ESGV) sont
  ventilés, comme dans ``backtest.data.exposure_vector``. C'est une approximation : l'indice du FNB n'est pas tout le
  marché américain, et le filtre ESG d'ESGV n'y est pas reflété ; les parts sectorielles concernées sont donc
  marquées HYPOTHESE.

Présentation des secteurs (choix documenté) :
- action individuelle : son secteur du jeu de départ (GICS), base ``direct`` ;
- FNB d'actions ventilable : ses 12 industries French ramenées aux mêmes clés de secteur, selon les tags que le
  catalogue ``assets.csv`` donne aux actifs ``US_IND_*`` (``KF_SECTOR``), base ``lookthrough`` ;
- FNB d'actions sans répartition disponible (XIU.TO, QQQ…) : clé ``non_ventile`` ; aucune répartition n'est inventée ;
- obligations, or, cryptoactifs : ce ne sont pas des secteurs d'actions ; ils gardent une clé propre (``obligations``,
  ``or_matieres``, ``crypto``), base ``direct``, pour que la part « actions par secteur » ne soit pas gonflée.
Parts publiées arrondies à 10 décimales et bornées à [0, 1], montants au cent ; les Facts ``mix.*`` portent
exactement ces valeurs (l'écran et les puces affichent la même chose).
Une clé qui reçoit à la fois une part directe et une part look-through (ex. ``tech`` : AAPL et SPY) a la base
``lookthrough`` ; le détail est dans le traitement (``processing``) de son Fact. ``sector_coverage`` = part du
portefeuille hors ``non_ventile``.

Bibliothèque standard seulement, sauf la lecture du look-through (pandas, à la demande) : testable en CI.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from alphaforge.finance.contracts.decision import Position, Source, Statement

from .facts import FactBook, fmt

STARTER_DATASET = "starter:assets_universe.csv"
MARKET_DATASET = "data/market/universe.yaml"
POSITIONS_DATASET = "decision:positions"
WEALTH_DATASET = "profil client : investable_wealth (CAD)"
LOOKTHROUGH_DATASET = (
    "alphaforge.finance.backtest:lookthrough_us_mkt.parquet (Kenneth R. French Data Library, 12 industries, "
    "part de la capitalisation américaine)"
)

# asset_class du jeu de départ -> (clé, libellé, texte dans une phrase, libellé du Fact)
CLASSES: dict[str, tuple[str, str, str, str]] = {
    "equity": (
        "actions_individuelles",
        "Actions individuelles",
        "actions individuelles",
        "Part des actions individuelles",
    ),
    "etf_equity": ("fnb_actions", "FNB d'actions", "FNB d'actions", "Part des FNB d'actions"),
    "etf_bond": (
        "obligations",
        "Obligations et quasi-liquidités",
        "obligations et quasi-liquidités",
        "Part des obligations et quasi-liquidités",
    ),
    "etf_commodity": (
        "or_matieres",
        "Or et matières premières",
        "or et matières premières",
        "Part de l'or et des matières premières",
    ),
    "crypto": ("crypto", "Cryptoactifs", "cryptoactifs", "Part des cryptoactifs"),
}
OTHER_CLASS = ("autres", "Autres actifs", "autres actifs", "Part des autres actifs")

CURRENCIES: dict[str, tuple[str, str]] = {
    "CAD": ("Dollar canadien (CAD)", "Part cotée en dollars canadiens"),
    "USD": ("Dollar américain (USD)", "Part cotée en dollars américains"),
}

# clé de secteur -> (libellé, libellé du Fact)
SECTORS: dict[str, tuple[str, str]] = {
    "tech": ("Technologie", "Part du secteur de la technologie"),
    "communication": ("Communications", "Part du secteur des communications"),
    "consumer_discretionary": ("Consommation discrétionnaire", "Part du secteur de la consommation discrétionnaire"),
    "consumer_staples": ("Consommation de base", "Part du secteur de la consommation de base"),
    "energy": ("Énergie", "Part du secteur de l'énergie"),
    "financials": ("Finance", "Part du secteur de la finance"),
    "healthcare": ("Santé", "Part du secteur de la santé"),
    "industrials": ("Industrie", "Part du secteur de l'industrie"),
    "materials": ("Matériaux", "Part du secteur des matériaux"),
    "utilities": ("Services publics", "Part du secteur des services publics"),
    "real_estate": ("Immobilier", "Part du secteur de l'immobilier"),
    "other": ("Autres industries", "Part des autres industries (classement Kenneth R. French)"),
    "obligations": ("Obligations et quasi-liquidités", "Part des obligations et quasi-liquidités (hors secteurs)"),
    "or_matieres": ("Or et matières premières", "Part de l'or et des matières premières (hors secteurs)"),
    "crypto": ("Cryptoactifs", "Part des cryptoactifs (hors secteurs)"),
    "non_ventile": ("Non ventilé", "Part non ventilée par secteur"),
}
NON_VENTILE = "non_ventile"

# Secteur du jeu de départ (GICS) -> clé.
GICS_SECTOR = {
    "Information Technology": "tech",
    "Communication Services": "communication",
    "Consumer Discretionary": "consumer_discretionary",
    "Consumer Staples": "consumer_staples",
    "Energy": "energy",
    "Financials": "financials",
    "Health Care": "healthcare",
    "Industrials": "industrials",
    "Materials": "materials",
    "Utilities": "utilities",
    "Real Estate": "real_estate",
}
# Industrie French (colonne de lookthrough_us_mkt.parquet) -> clé : le premier tag de secteur que assets.csv donne à
# l'actif US_IND_* correspondant. Correspondance approximative : les 12 industries French ne sont pas le GICS.
KF_SECTOR = {
    "US_IND_NODUR": "consumer_staples",
    "US_IND_DURBL": "consumer_discretionary",
    "US_IND_MANUF": "industrials",
    "US_IND_ENRGY": "energy",
    "US_IND_CHEMS": "materials",
    "US_IND_BUSEQ": "tech",
    "US_IND_TELCM": "communication",
    "US_IND_UTILS": "utilities",
    "US_IND_SHOPS": "consumer_discretionary",
    "US_IND_HLTH": "healthcare",
    "US_IND_MONEY": "financials",
    "US_IND_OTHER": "other",
}
# Classes qui ne sont pas des actions : leur propre clé, base « direct ».
CLASS_SECTOR = {"etf_bond": "obligations", "etf_commodity": "or_matieres", "crypto": "crypto"}


@dataclass(frozen=True)
class AssetMeta:
    asset_id: str
    name: str
    asset_class: str
    currency: str
    sector: str
    dataset: str  # d'où viennent ces métadonnées


@dataclass(frozen=True)
class Lookthrough:
    """Répartition par industrie French des FNB ventilables, et sa provenance."""

    shares: Mapping[str, Mapping[str, float]]  # actif -> {industrie US_IND_* : part}, somme 1
    month: str | None = None  # mois des parts utilisées (AAAA-MM-JJ)
    dataset: str = LOOKTHROUGH_DATASET


# ----------------------------------------------------------------------------- lectures (données réelles)
def asset_meta(asset_ids: Sequence[str]) -> dict[str, AssetMeta]:
    """Métadonnées de l'univers de marché (``alphaforge.market``, seule interface admise vers le jeu de départ) ; un
    actif absent de l'univers est absent du résultat. Les 31 actifs du jeu de départ (identifiants A01..A31, mêmes
    colonnes qu'``assets_universe.csv``) sont sourcés au jeu de départ, les autres à ``universe.yaml``."""
    from alphaforge import market

    universe = market.universe()
    out: dict[str, AssetMeta] = {}
    for a in asset_ids:
        row = universe.get(a)
        if row is not None:
            dataset = STARTER_DATASET if re.fullmatch(r"A\d{2}", row.asset_id) else MARKET_DATASET
            out[a] = AssetMeta(a, row.name, row.asset_class, row.currency, row.sector, dataset)
    return out


def load_lookthrough(asset_ids: Sequence[str], as_of: date) -> Lookthrough:
    """Parts par industrie des FNB que le moteur fait suivre à US_MKT, au dernier mois ≤ ``as_of``.

    Données absentes (CI sans données longues) : aucune ventilation, les FNB restent « non ventilé »."""
    try:
        import pandas as pd

        from alphaforge.finance.backtest import data as bt_data

        catalogue = bt_data.load_assets()
        table = bt_data.load_lookthrough()
    except Exception:
        return Lookthrough({})
    segment = table.loc[: bt_data.to_month_end(as_of)]
    if not len(segment):
        return Lookthrough({})
    row = segment.iloc[-1]
    cols = [c for c in KF_SECTOR if c in row.index and pd.notna(row[c])]
    total = float(sum(row[c] for c in cols))
    if total <= 0:
        return Lookthrough({})
    shares = {}
    for a in asset_ids:
        follows = a == "US_MKT" or (a in catalogue.index and catalogue.at[a, "proxy_for_ticker"] == "US_MKT")
        if follows:
            shares[a] = {c: float(row[c]) / total for c in cols}
    return Lookthrough(shares, month=str(segment.index[-1].date()))


# ----------------------------------------------------------------------------- calcul pur
def _sector_parts(meta: AssetMeta | None, asset_id: str, lt: Lookthrough) -> list[tuple[str, float, str]]:
    """(clé, part de la position, base) pour une position."""
    if meta is None:
        return [(NON_VENTILE, 1.0, NON_VENTILE)]
    if meta.asset_class in CLASS_SECTOR:
        return [(CLASS_SECTOR[meta.asset_class], 1.0, "direct")]
    if meta.asset_class == "equity":
        key = GICS_SECTOR.get(meta.sector)
        return [(key, 1.0, "direct")] if key else [(NON_VENTILE, 1.0, NON_VENTILE)]
    if meta.asset_class == "etf_equity" and asset_id in lt.shares:
        return [(KF_SECTOR[c], s, "lookthrough") for c, s in lt.shares[asset_id].items()]
    if meta.asset_class == "etf_equity" and meta.sector in GICS_SECTOR:  # FNB sectoriel (ex. XRE.TO, Real Estate)
        return [(GICS_SECTOR[meta.sector], 1.0, "direct")]
    return [(NON_VENTILE, 1.0, NON_VENTILE)]


SHARE_DECIMALS = 10  # bruit flottant des poids du solveur (1.0000000000000002) : une part reste dans [0, 1]
AMOUNT_DECIMALS = 2  # montants au cent


def _share(x: float) -> float:
    """Part publiée : arrondie à 10 décimales puis bornée à [0, 1] (le schéma de l'interface refuse toute part > 1)."""
    return min(max(round(float(x), SHARE_DECIMALS), 0.0), 1.0)


def _amount(weight: float, amount: float | None) -> float | None:
    """Montant publié, au cent : part publiée × montant de base."""
    return round(weight * amount, AMOUNT_DECIMALS) if amount is not None else None


def _sorted(rows: list[dict], last: str | None = None) -> list[dict]:
    return sorted(rows, key=lambda r: (r["key"] == last, -r["weight"], r["key"]))


def breakdown(
    positions: Sequence[Position],
    meta: Mapping[str, AssetMeta],
    lookthrough: Lookthrough,
    amount_cad: float | None,
) -> dict | None:
    """Répartition (sans Facts : ``fact_id`` vaut ``None``) ; ``None`` sans position."""
    if not positions:
        return None
    amount = round(float(amount_cad), AMOUNT_DECIMALS) if amount_cad else None
    pos_rows, classes, currencies = [], {}, {}
    sectors: dict[str, dict] = {}
    for p in positions:
        m = meta.get(p.asset_id)
        ckey, clabel, _, _ = CLASSES.get(m.asset_class, OTHER_CLASS) if m else OTHER_CLASS
        pos_rows.append(
            {
                "asset_id": p.asset_id,
                "name": m.name if m else p.asset_id,
                "asset_class": m.asset_class if m else None,
                "class_key": ckey,
                "currency": m.currency if m else None,
                "sector": m.sector if m else None,
                "role": p.role,
                "weight": _share(p.weight),
                "amount_cad": _amount(_share(p.weight), amount),
                "fact_id": None,
            }
        )
        c = classes.setdefault(ckey, {"key": ckey, "label_fr": clabel, "weight": 0.0, "assets": []})
        c["weight"] += p.weight
        c["assets"].append(p.asset_id)
        cur = m.currency if m and m.currency in CURRENCIES else "autre"
        lab = CURRENCIES[cur][0] if cur in CURRENCIES else "Autre devise"
        d = currencies.setdefault(cur, {"key": cur, "label_fr": lab, "weight": 0.0, "assets": []})
        d["weight"] += p.weight
        d["assets"].append(p.asset_id)
        for skey, share, basis in _sector_parts(m, p.asset_id, lookthrough):
            s = sectors.setdefault(
                skey,
                {
                    "key": skey,
                    "label_fr": SECTORS[skey][0],
                    "weight": 0.0,
                    "direct": 0.0,
                    "lookthrough": 0.0,
                    "assets": [],
                },
            )
            s["weight"] += p.weight * share
            s["lookthrough" if basis == "lookthrough" else "direct"] += p.weight * share
            if p.asset_id not in s["assets"]:
                s["assets"].append(p.asset_id)
    for s in sectors.values():
        s["basis"] = NON_VENTILE if s["key"] == NON_VENTILE else ("lookthrough" if s["lookthrough"] > 0 else "direct")
    groups = {"by_class": classes, "by_currency": currencies, "by_sector": sectors}
    out: dict = {"amount_cad": amount, "currency": "CAD", "positions": pos_rows}
    for name, rows in groups.items():
        for r in rows.values():
            for k in ("weight", "direct", "lookthrough"):
                if k in r:
                    r[k] = _share(r[k])
        out[name] = _sorted(
            [{**r, "amount_cad": _amount(r["weight"], amount), "fact_id": None} for r in rows.values()],
            last=NON_VENTILE if name == "by_sector" else None,
        )
    out["sector_coverage"] = _share(sum(s["weight"] for s in sectors.values() if s["key"] != NON_VENTILE))
    return out


_PUBLIC = {
    "positions": (
        "asset_id",
        "name",
        "asset_class",
        "class_key",
        "currency",
        "sector",
        "role",
        "weight",
        "amount_cad",
        "fact_id",
    ),
    "by_class": ("key", "label_fr", "weight", "amount_cad", "fact_id"),
    "by_currency": ("key", "label_fr", "weight", "amount_cad", "fact_id"),
    "by_sector": ("key", "label_fr", "weight", "amount_cad", "fact_id", "basis"),
}


def _public(alloc: dict) -> dict:
    """Seulement les clés du contrat (CONTRACTS.md §12) ; les champs de travail restent internes."""
    out = dict(alloc)
    for name, keys in _PUBLIC.items():
        out[name] = [{k: r[k] for k in keys} for r in alloc[name]]
    return out


# ----------------------------------------------------------------------------- Facts
def _pct(x: float) -> str:
    return fmt(x, "%")


def _add_facts(book: FactBook, alloc: dict, meta: Mapping[str, AssetMeta], lt: Lookthrough) -> None:
    def meta_source(assets: list[str]) -> str:
        found = sorted({meta[a].dataset for a in assets if a in meta})
        return " + ".join(found) or "actif hors univers"

    def add(key, label, value, unit, *, dataset, processing, extra=(), status="FAIT", currency=None) -> str:
        fid = book.add(
            key, label, value, unit, dataset=dataset, processing=processing, status=status, currency=currency
        )
        for ds, proc in extra:
            book.facts[fid].sources.append(Source(dataset=ds, processing=proc))
        return fid

    weights = "poids finaux normalisés des positions de la décision (somme 1)"
    if alloc["amount_cad"] is not None:
        add(
            "mix.amount_total",
            "Montant de base de la répartition",
            alloc["amount_cad"],
            "CAD",
            dataset=WEALTH_DATASET,
            processing="patrimoine investissable déclaré, en CAD",
            currency="CAD",
        )
        for r in alloc["positions"]:
            r["fact_id"] = add(
                f"mix.amount.{r['asset_id']}",
                f"Montant placé dans {r['asset_id']}",
                r["amount_cad"],
                "CAD",
                dataset=POSITIONS_DATASET,
                processing=f"poids {_pct(r['weight'])} × montant de base",
                extra=[(WEALTH_DATASET, "montant de base")],
                currency="CAD",
            )
    for r in alloc["by_class"]:
        _, _, _, label = next((v for v in CLASSES.values() if v[0] == r["key"]), OTHER_CLASS)
        r["fact_id"] = add(
            f"mix.class.{r['key']}",
            label,
            r["weight"],
            "%",
            dataset=STARTER_DATASET,
            processing=f"somme des poids de {', '.join(r['assets'])} (asset_class)",
            extra=[(POSITIONS_DATASET, weights)]
            + (
                [(MARKET_DATASET, "asset_class hors jeu de départ")]
                if MARKET_DATASET in meta_source(r["assets"])
                else []
            ),
        )
    for r in alloc["by_currency"]:
        label = CURRENCIES[r["key"]][1] if r["key"] in CURRENCIES else "Part cotée dans une autre devise"
        r["fact_id"] = add(
            f"mix.currency.{r['key']}",
            label,
            r["weight"],
            "%",
            dataset=STARTER_DATASET,
            processing=f"devise de cotation de {', '.join(r['assets'])} ; somme de leurs poids (exposition de "
            "change avant conversion en CAD)",
            extra=[(POSITIONS_DATASET, weights)],
        )
    for r in alloc["by_sector"]:
        lt_part = r["lookthrough"] > 0
        proc = f"positions : {', '.join(r['assets'])}"
        if r["key"] == NON_VENTILE:
            proc += " ; aucune répartition sectorielle disponible, aucune n'est supposée"
        elif lt_part:
            proc += (
                f" ; part directe {_pct(r['direct'])} + transparence des FNB {_pct(r['lookthrough'])} "
                f"(industries French au {lt.month}, FNB suivant le marché américain US_MKT : approximation)"
            )
        extra = [(POSITIONS_DATASET, weights)]
        if lt_part:
            extra.append((lt.dataset, f"parts par industrie au {lt.month}, correspondance KF_SECTOR"))
        r["fact_id"] = add(
            f"mix.sector.{r['key']}",
            SECTORS[r["key"]][1],
            r["weight"],
            "%",
            dataset=STARTER_DATASET,
            processing=proc,
            extra=extra,
            status="HYPOTHESE" if lt_part else "FAIT",
        )


def allocation_breakdown(
    book: FactBook,
    positions: Sequence[Position],
    amount_cad: float | None,
    as_of: date,
    *,
    meta_fn: Callable[[Sequence[str]], Mapping[str, AssetMeta]] = asset_meta,
    lookthrough_fn: Callable[[Sequence[str], date], Lookthrough] = load_lookthrough,
) -> dict | None:
    """Répartition de la décision, avec ses Facts (étape tracée ``allocation``) ; ``None`` sans position.

    ``positions`` : les positions FINALES (normalisées) de la décision. Résultat sérialisable en JSON (contrat
    ``BuildResult.allocation``, CONTRACTS.md §12)."""
    if not positions:
        return None
    ids = [p.asset_id for p in positions]
    with book.step("allocation", tool="allocation_breakdown", inputs={"assets": ids, "amount_cad": amount_cad}) as ev:
        meta = meta_fn(ids)
        lt = lookthrough_fn(ids, as_of)
        alloc = breakdown(positions, meta, lt, amount_cad)
        _add_facts(book, alloc, meta, lt)
        ev.output_summary = (
            f"{len(alloc['by_class'])} classes, {len(alloc['by_currency'])} devises, {len(alloc['by_sector'])} "
            f"secteurs ; couverture sectorielle {_pct(alloc['sector_coverage'])}"
        )
    return _public(alloc)


def allocation_statement(book: FactBook, alloc: dict) -> Statement:
    """« Répartition de l'argent : FNB d'actions 69,0 %, … » ; chaque nombre est la valeur formatée d'un Fact cité."""
    texts = {v[0]: v[2] for v in (*CLASSES.values(), OTHER_CLASS)}
    parts = []
    for r in alloc["by_class"]:
        f = book.facts[r["fact_id"]]
        parts.append(f"{texts[r['key']]} {fmt(f.value, f.unit)}")
    return Statement(
        text_fr="Répartition de l'argent : " + ", ".join(parts) + ".",
        fact_ids=[r["fact_id"] for r in alloc["by_class"]],
    )
