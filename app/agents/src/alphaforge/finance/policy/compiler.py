"""F1 — compilateur deterministe InvestorProfile -> PolicySpec (risk_levels.yaml v0.2).

Porte en code de bibliotheque la logique de app/agents/scripts/calibration/review/expand.py (emit) et
persona_v02.py (capacite, tolerance, regle des dollars). Chaque nombre derive est inscrit dans
``trace`` avec son chemin YAML ; chaque Limit porte ``source = risk_levels.yaml@<ver>#<chemin>``.
SIMULATION SEULEMENT — jamais un conseil financier.
"""

from __future__ import annotations

import hashlib
import json
import math
import unicodedata
from datetime import UTC, date, datetime, time
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from alphaforge.finance.contracts import ExposureOverride, HistoryProxy, Limit, PolicySpec, Selector
from alphaforge.finance.contracts.profile import InvestorProfile, ProfileStatus, Score

from . import envelope as ENV
from .adapter import QuestionnaireScores, apply_questionnaire
from .emphasis import compute_emphasis
from .models import CompileResult, RequestView, SpecificRequest

LV = ["N0", "N1", "N2", "N3", "N4", "N5"]
DEFAULT_YAML = Path(__file__).with_name("risk_levels.yaml")
EPS = 1e-12

# Constantes absentes du YAML sous forme de cle (presentes dans le texte du YAML) : tracees comme telles.
MU_RECOVERY = 0.04  # risk_levels.yaml#dollar_rule.l_cap : « mu_recovery 0.04 (HYPOTHESE) »
CONCENTRATION_SHARE = 0.10  # signal d'emphase seulement (pas une limite)

# Classes d'actifs du starter (copie de assets.csv du moteur alphaforge.finance.backtest, colonne asset_class),
# utilisees seulement pour classer une SpecificRequest ; surchargeables via ``asset_classes``.
STARTER_ASSET_CLASSES = {
    **{t: "etf_equity" for t in ("XIU.TO", "SPY", "QQQ", "ESGV")},
    **{t: "etf_bond" for t in ("XBB.TO", "ZST.TO", "AGG", "TLT")},
    "GLD": "commodity",
    "BTC-USD": "crypto",
    "ETH-USD": "crypto",
    **{
        t: "equity_single"
        for t in (
            "RY.TO",
            "TD.TO",
            "MFC.TO",
            "ENB.TO",
            "CNQ.TO",
            "CNR.TO",
            "FTS.TO",
            "ATD.TO",
            "SHOP.TO",
            "CSU.TO",
            "AAPL",
            "MSFT",
            "NVDA",
            "GOOGL",
            "AMZN",
            "TSLA",
            "JPM",
            "JNJ",
            "PG",
            "XOM",
        )
    },
}
CRYPTO_ETF_CLASSES = {"etf_crypto"}  # aucun dans le starter -> crypto « etf_only » = 0 pour un debutant
CRYPTO_TILT_WORDS = ("crypto", "bitcoin", "btc", "ether", "eth")


# --------------------------------------------------------------------------- utilitaires


def _clip(x: float, a: float = 0.0, b: float = 1.0) -> float:
    return max(a, min(b, x))


def floor_step(x: float, s: float = 0.0025) -> float:
    return round(math.floor(round(x / s, 9)) * s, 6)


def ceil_step(x: float, s: float) -> float:
    return round(math.ceil(round(x / s, 9)) * s, 6)


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return s.replace("-", "_").replace(" ", "_")


def _bias_key(label: str) -> str | None:
    s = _norm(label)
    if "fomo" in s:
        return "FOMO"
    if "surconf" in s or "overconf" in s:
        return "surconfiance"
    if "aversion" in s or "loss_aver" in s:
        return "aversion_perte"
    if "familiar" in s or "home_bias" in s:
        return "familiarite"
    return None


@lru_cache(maxsize=8)
def _load_yaml(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _lvl_idx(L: str) -> int:
    return LV.index(L)


class _Ctx:
    def __init__(self, Y: dict):
        self.Y = Y
        self.ver = str(Y["version"])
        self.trace: list[dict[str, Any]] = []
        self.missing: list[str] = []

    def src(self, path: str) -> str:
        return f"risk_levels.yaml@{self.ver}#{path}"

    def t(self, rule: str, inputs: dict, output: Any, path: str) -> Any:
        self.trace.append(
            {
                "rule": rule,
                "inputs": inputs,
                "output": output,
                "yaml_path": path
                if path.startswith(("risk_levels", "envelope", "emphasis", "profile", "questionnaire"))
                else self.src(path),
            }
        )
        return output

    def default(self, field: str, value: Any, why: str) -> Any:
        self.missing.append(f"{field} absent -> {value!r} ({why})")
        return value


# --------------------------------------------------------------------------- faits du profil


def _goal_horizon(g, as_of: date) -> float:
    hs = []
    if g.horizon_years is not None:
        hs.append(float(g.horizon_years))
    if g.target_date is not None:
        hs.append(max(0.0, (g.target_date - as_of).days / 365.25))
    return min(hs)


def _is_retired(p: InvestorProfile) -> bool:
    no_income = p.income is None or not p.income.annual_amount
    return no_income and bool(p.pensions)


def _horizon_and_buckets(p: InvestorProfile, as_of: date, c: _Ctx, opts: dict) -> tuple[float, str | None, list[dict]]:
    """T du seau risque, plafond de niveau impose par les seaux (si tous les objectifs sont « seau »)."""
    rules = c.Y["buckets"]["rules"]
    reserve_years = c.Y["buckets"]["withdrawal_reserve_years"]
    buckets, risk_h, caps = [], [], []
    covered = opts.get("covered_goal_ids") or set()
    seq = opts.get("sequence_reserve_years")
    if opts.get("liquid_pocket_cad"):
        buckets.append(
            {
                "goal_id": "poche_liquide",
                "level_cap": opts["bucket_level"],
                "amount": opts["liquid_pocket_cad"],
                "covers": sorted(covered),
                "kind": "poche_liquide",
                "source": "questionnaire_adapter.yaml#liquid_pocket",
            }
        )
    for g in p.goals:
        h = _goal_horizon(g, as_of)
        if g.goal_id in covered:  # finance par la poche liquide : hors du seau risque (un seul chemin)
            continue
        match = [(i, r) for i, r in enumerate(rules) if r["priority"] == g.priority.value and h <= r["T_max"]]
        if match:
            i, r = min(match, key=lambda m: _lvl_idx(m[1]["level_cap"]))
            buckets.append(
                {
                    "goal_id": g.goal_id,
                    "horizon_years": round(h, 4),
                    "level_cap": r["level_cap"],
                    "amount": g.amount,
                    "source": c.src(f"buckets.rules[{i}]"),
                }
            )
            caps.append(r["level_cap"])
            c.t(
                "buckets.goal",
                {"goal_id": g.goal_id, "priority": g.priority.value, "horizon_years": h},
                r["level_cap"],
                f"buckets.rules[{i}]",
            )
            continue
        if g.recurring_withdrawal and seq:  # reserve deja dans la poche liquide du questionnaire
            h = h + seq
            c.t(
                "buckets.withdrawal_reserve",
                {"goal_id": g.goal_id, "sequence_reserve_years": seq},
                {"risk_horizon_years": h},
                "questionnaire_adapter.yaml#liquid_pocket",
            )
        elif g.recurring_withdrawal and h <= 5:
            buckets.append(
                {
                    "goal_id": g.goal_id,
                    "horizon_years": round(h, 4),
                    "level_cap": "N1",
                    "amount": reserve_years * g.recurring_withdrawal,
                    "kind": "reserve_retraits",
                    "source": c.src("buckets.withdrawal_reserve_years"),
                }
            )
            h = h + reserve_years
            c.t(
                "buckets.withdrawal_reserve",
                {"goal_id": g.goal_id, "recurring_withdrawal": g.recurring_withdrawal},
                {"reserve_cad": reserve_years * g.recurring_withdrawal, "risk_horizon_years": h},
                "buckets.withdrawal_reserve_years",
            )
        risk_h.append(h)
    if risk_h:
        T = min(risk_h)
        cap = None
    else:  # tous les objectifs sont des seaux prudents : le mandat entier suit le plus strict
        T = min(_goal_horizon(g, as_of) for g in p.goals if g.goal_id not in covered)
        cap = min(caps, key=_lvl_idx)
    c.t(
        "horizon.T_risk",
        {"goal_horizons": {g.goal_id: round(_goal_horizon(g, as_of), 4) for g in p.goals}},
        round(T, 4),
        "horizon_cap",
    )
    return T, cap, buckets


# --------------------------------------------------------------------------- capacite


def _capacity(p: InvestorProfile, T: float, W: float | None, c: _Ctx, opts: dict) -> tuple[dict, float]:
    Y = c.Y["capacity"]
    w = Y["weights"]
    # H : horizon
    hz = Y["horizon"]
    cH = _clip(math.log(T / hz["T_zero"]) / math.log(hz["T_full"] / hz["T_zero"])) if T > 0 else 0.0
    c.t("capacity.H", {"T": T}, cH, "capacity.horizon")
    # E : reserve d'urgence
    retired = _is_retired(p)
    req = Y["emergency_req_months"]
    var = p.income.variability if p.income else None
    if retired:
        Ereq = req["retraite_ou_55plus"]
    elif var is None:
        Ereq = c.default("income.variability", max(req.values()), "capacity.emergency_req_months : plus exigeant")
    else:
        Ereq = req[var]
    if p.age is not None and p.age >= 55:
        Ereq = max(Ereq, req["retraite_ou_55plus"])
    E = p.emergency_fund_months
    if E is None:
        E = c.default("emergency_fund_months", 0.0, "prudent : aucune reserve supposee")
    cE = _clip(E / Ereq)
    c.t(
        "capacity.E",
        {"emergency_fund_months": E, "required_months": Ereq, "retired": retired},
        cE,
        "capacity.emergency_req_months",
    )
    # D : retraits
    wd = Y["withdrawal"]
    covered = opts.get("covered_goal_ids") or set()
    withdrawals = sum(g.recurring_withdrawal or 0.0 for g in p.goals if g.goal_id not in covered)
    if withdrawals and not W:
        q = c.default("investable_wealth (taux de retrait)", wd["q_max"], "q = q_max, prudent")
    else:
        q = withdrawals / W if W else 0.0
    cD = _clip(1 - wd["phi_dep"] * q / wd["q_max"])
    c.t("capacity.D", {"annual_withdrawals": withdrawals, "W": W, "q": q}, cD, "capacity.withdrawal")
    # A : absorption (l_cap)
    l_cap = max(0.0, min(1 - q / wd["q_max"], 1 - (1 + MU_RECOVERY) ** (-T)))
    c.t(
        "dollar_rule.l_cap",
        {"q": q, "q_max": wd["q_max"], "T": T, "mu_recovery": MU_RECOVERY},
        l_cap,
        "dollar_rule.l_cap",
    )
    cA = _clip(l_cap / Y["absorption_full"])
    c.t("capacity.A", {"l_cap": l_cap}, cA, "capacity.absorption_full")
    # I : stabilite du revenu
    st = Y["income_stability"]
    if retired:
        pension_m = sum(x.monthly_amount or 0.0 for x in p.pensions)
        M = p.monthly_expenses
        pi = _clip(pension_m / M) if M else c.default("monthly_expenses (couverture des rentes)", 0.0, "pi = 0")
        cI = 0.3 + 0.7 * pi
        c.t(
            "capacity.I.retired",
            {"pension_monthly": pension_m, "monthly_expenses": M, "pi": pi},
            cI,
            "capacity.income_stability.retired",
        )
    elif var is None:
        cI = st["missing"]
        c.t("capacity.I", {"variability": None}, cI, "capacity.income_stability.missing")
    else:
        cI = st[var]
        c.t("capacity.I", {"variability": var}, cI, f"capacity.income_stability.{var}")
    if p.employer_equity:
        cI *= Y["employer_equity_haircut"]
        c.t(
            "capacity.I.employer_haircut",
            {"employer_equity": len(p.employer_equity)},
            cI,
            "capacity.employer_equity_haircut",
        )
    # L : dette hors hypotheque / revenu
    nm_debt = sum(d.balance for d in p.debts if not any(k in _norm(d.label) for k in ("hypoth", "mortgage")))
    inc = (p.income.annual_amount if p.income and p.income.annual_amount else 0.0) or 12 * sum(
        x.monthly_amount or 0.0 for x in p.pensions
    )
    if inc:
        cL = _clip(1 - nm_debt / inc)
    else:
        cL = c.default("income.annual_amount", 0.5, "capacity : cL neutre 0.5 (persona.py)") if nm_debt else 1.0
    c.t("capacity.L", {"non_mortgage_debt": nm_debt, "annual_income": inc}, cL, "capacity.weights.L")

    comps = {"H": cH, "A": cA, "E": cE, "D": cD, "I": cI, "L": cL}
    C_raw = 100 * math.prod(max(comps[k], 0.05) ** w[k] for k in w)
    c.t("capacity.C", {"components": comps, "weights": w}, C_raw, "capacity.weights")
    C, applied = C_raw, []
    hc = Y["hard_caps"]
    if E < 1:
        C = min(C, hc["emergency_lt_1_month"])
        applied.append("emergency_lt_1_month")
        c.t("capacity.hard_cap", {"emergency_fund_months": E}, C, "capacity.hard_caps.emergency_lt_1_month")
    high = [d.label for d in p.debts if d.annual_rate >= Y["debt"]["high_cost_rate"] and d.balance > 0]
    if high:
        C = min(C, Y["debt"]["high_cost_cap"])
        applied.append("high_cost_debt")
        c.t("capacity.hard_cap", {"high_cost_debts": high}, C, "capacity.debt.high_cost_cap")
    under = [
        g.goal_id
        for g in p.goals
        if g.priority.value == "besoin" and g.amount and W is not None and g.amount > W and (g.horizon_years or 99) <= 5
    ]
    if under:
        C = min(C, hc["besoin_underfunded"])
        applied.append("besoin_underfunded")
        c.t(
            "capacity.hard_cap", {"underfunded_besoin_goals": under, "W": W}, C, "capacity.hard_caps.besoin_underfunded"
        )
    if p.capacity_assessed is not None and Y.get("never_exceed_capacity_assessed", True):
        if p.capacity_assessed.value < C:
            applied.append("capacity_assessed")
        C = min(C, p.capacity_assessed.value)
        c.t(
            "capacity.assessed",
            {"capacity_assessed": p.capacity_assessed.value},
            C,
            "capacity.never_exceed_capacity_assessed",
        )
    out = {
        "C": C,
        "C_raw": C_raw,
        "components": comps,
        "hard_caps_applied": applied,
        "emergency_required_months": Ereq,
        "q": q,
        "l_cap": l_cap,
        "retired": retired,
    }
    return out, l_cap


# --------------------------------------------------------------------------- tolerance


def _tol_one(
    declared: Score | None, tested: Score | None, composure: Score | None, c: _Ctx, overconfident: bool, who: str
) -> dict:
    Y = c.Y["tolerance"]
    dc = Y["default_confidence"]
    wD, wX = Y["w_declared"], Y["w_tested"]
    mult = 1.0
    if overconfident:
        b = c.Y["biases"]["surconfiance"]
        wX, mult = b["w_tested"], b["declared_confidence_mult"]
    T0 = Y["conservative_prior"]
    parts = []
    if declared is not None:
        kD = (declared.confidence if declared.confidence is not None else dc["declared"]) * mult
        parts.append(("declared", declared.value, wD, kD))
    if tested is not None:
        kX = tested.confidence if tested.confidence is not None else dc["tested"]
        parts.append(("tested", tested.value, wX, kX))
    if not parts:
        return {"T": float(T0), "steps": {"prior": T0}, "who": who, "missing": True}
    Tb = sum(w * k * v for _, v, w, k in parts) / sum(w * k for _, v, w, k in parts)
    if len(parts) == 2:
        dis = Y["disagreement"]
        D, X = parts[0][1], parts[1][1]
        beta = _clip((abs(D - X) - dis["free"]) / (dis["full"] - dis["free"]))
        T1 = (1 - beta) * Tb + beta * min(D, X)
    else:
        beta, T1 = 0.0, Tb
    k = 1 - math.prod(1 - kk for *_, kk in parts)
    T2 = T1 - (1 - k) * max(0.0, T1 - T0)
    cp = Y["composure"]
    if composure is not None:
        T3 = T2 - cp["slope"] * max(0.0, T2 - (composure.value + cp["slack"]))
    else:
        T3 = T2 - cp["missing_penalty"]
    return {
        "T": T3,
        "who": who,
        "missing": False,
        "overconfident": overconfident,
        "steps": {"Tb": Tb, "beta": beta, "T1": T1, "k": k, "T2": T2, "T3": T3},
    }


def _tolerance(p: InvestorProfile, biases: set[str], c: _Ctx) -> dict:
    base = _tol_one(p.tolerance_declared, p.tolerance_tested, p.composure, c, False, "personne")
    c.t(
        "tolerance.person",
        {
            "declared": p.tolerance_declared and p.tolerance_declared.value,
            "tested": p.tolerance_tested and p.tolerance_tested.value,
            "composure": p.composure and p.composure.value,
        },
        base["steps"],
        "tolerance",
    )
    if base["missing"]:
        c.default("tolerance_declared/tolerance_tested", base["T"], "tolerance.conservative_prior")
    if p.composure is None:
        c.default("composure", -c.Y["tolerance"]["composure"]["missing_penalty"], "tolerance.composure.missing_penalty")
    T, cands = base["T"], [base]
    if "surconfiance" in biases:  # les biais ne font que resserrer : min(sans, avec)
        oc = _tol_one(p.tolerance_declared, p.tolerance_tested, p.composure, c, True, "personne+surconfiance")
        c.t("biases.surconfiance", {"T_without": T, "T_with": oc["T"]}, min(T, oc["T"]), "biases.surconfiance")
        T = min(T, oc["T"])
        cands.append(oc)
    members = [m for m in p.household if m.tolerance is not None]
    if members:
        rule = p.household_rule or "min_tolerance"
        for m in members:
            mt = _tol_one(m.tolerance, None, None, c, False, m.role)
            c.t(
                "household.member",
                {"role": m.role, "tolerance": m.tolerance.value, "rule": rule},
                mt["T"],
                "household.min_tolerance",
            )
            T = min(T, mt["T"])
            cands.append(mt)
    c.t("tolerance.T", {"candidates": [x["T"] for x in cands]}, T, "household.min_tolerance")
    return {"T": T, "person": base, "candidates": cands}


# --------------------------------------------------------------------------- niveau


def _level_of_R(R: float, cut: list[float]) -> int:
    return sum(R >= x for x in cut)


def _horizon_cap(T: float, c: _Ctx) -> str:
    for i, r in enumerate(c.Y["horizon_cap"]):
        if r["T_lt"] is None or T < r["T_lt"]:
            c.t("horizon_cap", {"T": T}, r["level_max"], f"horizon_cap[{i}]")
            return r["level_max"]
    raise ValueError("horizon_cap sans ligne terminale")


def _band(L: str, c: _Ctx) -> tuple[int, int]:
    a, b = c.Y["levels"][L]["equity"]
    return int(round(a * 100)), int(round(b * 100))


def _budgets(L: str, e_cap: int, c: _Ctx) -> dict[str, tuple[float, str]]:
    """Budgets de risque du niveau ; si e_cap < e_max : arrondi_sup(ENV(e_cap)) (budgets_when_capped)."""
    lev = c.Y["levels"][L]
    keys = {"vol": "vol", "cvar_m": "cvar95_m", "cvar_12m": "cvar95_12m", "mdd": "mdd", "s2022": "y2022"}
    if e_cap >= _band(L, c)[1]:
        return {k: (float(lev[k]), c.src(f"levels.{L}.{k}")) for k in keys}
    rnd = c.Y["measurement"]["rounding"]
    out = {}
    for k, col in keys.items():
        # Garde de monotonie (ecart au YAML) : ENV n'est pas monotone sous e = 10 % (obligations seules
        # plus dures que le melange demi-cash) ; un budget plafonne ne depasse jamais celui du niveau.
        v = min(ceil_step(ENV.env(e_cap, col), rnd[k]), float(lev[k]))
        out[k] = (v, f"{c.src('levels.budgets_when_capped')} ; envelope_v02.yaml#equity_pct.{e_cap}.{col}")
        c.t(
            f"budget.{k}",
            {"e_cap_pct": e_cap, "env": ENV.env(e_cap, col), "step": rnd[k], "level_budget": lev[k]},
            v,
            c.src("levels.budgets_when_capped"),
        )
    return out


# --------------------------------------------------------------------------- compilateur


def _universe(Y: dict) -> list[str]:
    return list(Y["history_proxies"]) + [a for a in Y.get("no_proxy") or [] if a not in Y["history_proxies"]]


def _signature(profile: InvestorProfile, as_of: date, request, Y: dict, universe: list[str], questionnaire=None) -> str:
    blob = json.dumps(
        {
            "profile": profile.model_dump(mode="json"),
            "as_of": as_of.isoformat(),
            "questionnaire": questionnaire.model_dump(mode="json") if questionnaire else None,
            "request": request.model_dump(mode="json") if request else None,
            "yaml_version": Y["version"],
            "universe": universe,
        },
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def compile_profile(
    profile: InvestorProfile,
    as_of: date,
    *,
    request: SpecificRequest | None = None,
    yaml_path: str | Path | None = None,
    universe: list[str] | None = None,
    asset_classes: dict[str, str] | None = None,
    emphasis_path: str | Path | None = None,
    questionnaire: QuestionnaireScores | None = None,
) -> CompileResult:
    """Compile un profil en mandat PolicySpec. Deterministe : memes entrees -> meme JSON."""
    Y = _load_yaml(str(yaml_path or DEFAULT_YAML))
    c = _Ctx(Y)
    p = profile
    opts: dict = {}
    if questionnaire is not None:
        p, opts, qtrace = apply_questionnaire(p, questionnaire)
        c.trace.extend(qtrace)
        c.missing.extend(opts["notes"])
    classes = {**STARTER_ASSET_CLASSES, **(asset_classes or {})}
    uni = list(universe) if universe is not None else _universe(Y)

    biases = {k for k in (_bias_key(b.kind_label) for b in p.biases) if k}
    knowledge = p.knowledge_level.value if p.knowledge_level else None
    if knowledge is None:
        knowledge = c.default("knowledge_level", Y["knowledge"]["missing"], "knowledge.missing")
    kn = Y["knowledge"].get(knowledge) or {}

    # ---- statut
    W = p.investable_wealth
    must_missing = [f for f in Y["status"]["must_have"] if f == "investable_wealth" and W is None]
    status = p.status.value
    if status == "COMPLETE" and (
        must_missing or (p.confidence is not None and p.confidence < Y["status"]["completeness_min"])
    ):
        status = "INCOMPLETE"
    c.t(
        "status",
        {"profile_status": p.status.value, "must_have_missing": must_missing, "confidence": p.confidence},
        status,
        "status",
    )
    if W is None:
        c.default("investable_wealth", None, "status.must_have : aucun calcul en dollars")

    # ---- horizon, capacite, tolerance, R
    T, bucket_cap, buckets = _horizon_and_buckets(p, as_of, c, opts)
    cap, l_cap = _capacity(p, T, W, c, opts)
    C = cap["C"]
    tol = _tolerance(p, biases, c)
    Tval = tol["T"]
    fp = Y["tolerance"]["flag_penalty"]
    penalty = min(fp["max"], fp["per_flag"] * len(p.consistency_flags))
    R = min(Tval, C) - penalty
    c.t("R", {"T": Tval, "C": C, "flag_penalty": penalty, "flags": list(p.consistency_flags)}, R, "R")
    cut = Y["levels"]["R_cutoffs"]
    iR = _level_of_R(R, cut)
    c.t("level.R", {"R": R, "cutoffs": cut}, LV[iR], "levels.R_cutoffs")
    near = min(abs(R - x) for x in cut) < Y["levels"]["hysteresis"]

    # ---- plafonds : horizon, seaux, statut
    caps = {"R": iR, "horizon": _lvl_idx(_horizon_cap(T, c))}
    if bucket_cap:
        caps["buckets"] = _lvl_idx(bucket_cap)
    if status == "INCOMPLETE":
        caps["status"] = _lvl_idx(Y["status"]["INCOMPLETE"]["level_cap"])
        c.t("status.INCOMPLETE.level_cap", {}, Y["status"]["INCOMPLETE"]["level_cap"], "status.INCOMPLETE.level_cap")
    i0 = min(caps.values())
    c.t("level.L0", caps, LV[i0], "R")

    # ---- regle des dollars
    buf = Y["dollar_rule"]["daily_buffer"]
    Lp = lambda e: ENV.env(e, "mdd") + buf  # noqa: E731
    emax = _band(LV[i0], c)[1]
    l_decl_parts = []
    if p.max_acceptable_loss_pct is not None:
        l_decl_parts.append(p.max_acceptable_loss_pct)
    if p.max_acceptable_loss_cad is not None and W:
        l_decl_parts.append(p.max_acceptable_loss_cad / W)
    l_decl = min(l_decl_parts) if l_decl_parts else None
    c.t(
        "dollar_rule.l_declared",
        {"pct": p.max_acceptable_loss_pct, "cad": p.max_acceptable_loss_cad, "W": W},
        l_decl,
        "dollar_rule.l_declared",
    )
    l_star = min(x for x in (Lp(emax), l_decl, l_cap) if x is not None)
    c.t(
        "dollar_rule.l_star",
        {
            "L_plan_emax": Lp(emax),
            "l_declared": l_decl,
            "l_cap": l_cap,
            "e_max_pct": emax,
            "daily_buffer": buf,
            "envelope": f"envelope_v02.yaml#equity_pct.{emax}.mdd",
        },
        l_star,
        "dollar_rule.l_star",
    )
    ok = [e for e in ENV.grid() if e <= emax and Lp(e) <= l_star + EPS]
    protection = p.status is ProfileStatus.PROTECTION or not ok
    if not ok:
        c.t(
            "dollar_rule.protection",
            {"l_star": l_star, "min_L_plan": min(Lp(e) for e in ENV.grid())},
            "PROTECTION",
            "dollar_rule.protection",
        )
        e_cap = 0
    else:
        e_cap = max(ok)
        c.t(
            "dollar_rule.e_cap",
            {"l_star": l_star, "e_max_pct": emax, "L_plan_e_cap": Lp(e_cap)},
            e_cap,
            "dollar_rule.e_cap",
        )
    if e_cap == 0:
        i = 0
    else:
        i = next(k for k, L in enumerate(LV) if _band(L, c)[0] < e_cap <= _band(L, c)[1])
    i = min(i, i0)
    if protection:
        i = _lvl_idx(Y["status"]["PROTECTION"]["level"])
        e_cap = min(e_cap, _band(LV[i], c)[1]) if ok else 0
        status = "PROTECTION"
    L = LV[i]
    c.t("level.final", {"e_cap_pct": e_cap, "L0": LV[i0], "protection": protection}, L, "dollar_rule.level_after")
    e_min = _band(L, c)[0]

    # ---- satellites
    S = Y["satellites"]
    status_zero = Y["status"].get(status, {}) if status in ("INCOMPLETE", "PROTECTION") else {}
    sn = S["single_name"]
    if i < _lvl_idx(sn["min_level"]) or status_zero.get("single_name") == 0:
        w_single = w_single_total = 0.0
        single_src = c.src(f"status.{status}.single_name") if status_zero else c.src("satellites.single_name.min_level")
    else:
        w_single = min(sn["cap_abs"], floor_step(sn["phi"] * l_star / sn["delta"]))
        w_single_total = floor_step(sn["total_phi"] * l_star / sn["delta"])
        single_src = c.src("satellites.single_name")
        if "single_name_cap" in kn:
            w_single = min(w_single, kn["single_name_cap"])
            single_src += f" ; {c.src(f'knowledge.{knowledge}.single_name_cap')}"
    c.t(
        "satellites.single_name",
        {"level": L, "l_star": l_star, "knowledge": knowledge, "status": status},
        {"each": w_single, "total": w_single_total},
        single_src.split(" ; ")[0],
    )

    cr = S["crypto"]
    tilt = any(any(wd in _norm(t) for wd in CRYPTO_TILT_WORDS) for t in p.preferences.tilts)
    crypto_src = c.src("satellites.crypto")
    if i < _lvl_idx(cr["min_level"]) or (cr["requires_tilt"] and not tilt) or status_zero.get("crypto") == 0:
        w_crypto = 0.0
    else:
        w_crypto = min(cr["cap_abs"][L], floor_step(cr["phi"] * l_star / cr["delta"]))
        if "crypto_mult" in kn:
            w_crypto = floor_step(w_crypto * kn["crypto_mult"])
            crypto_src += f" ; {c.src(f'knowledge.{knowledge}.crypto_mult')}"
        if kn.get("crypto_vehicle") == "etf_only" and not any(classes.get(a) in CRYPTO_ETF_CLASSES for a in uni):
            w_crypto = 0.0
            crypto_src += f" ; {c.src(f'knowledge.{knowledge}.crypto_vehicle')} (aucun FNB crypto dans l'univers)"
    c.t(
        "satellites.crypto",
        {"level": L, "tilt": tilt, "l_star": l_star, "knowledge": knowledge},
        w_crypto,
        crypto_src.split(" ; ")[0],
    )

    sb = S["sandbox"]
    M = p.monthly_expenses
    if i < _lvl_idx(sb["min_level"]) or status_zero.get("sandbox") == 0 or not W:
        w_sandbox = 0.0
    else:
        if M is None:
            M = c.default("monthly_expenses", 0.0, "satellites.sandbox.months_cap : bac a sable nul")
        w_sandbox = min(
            sb["cap_abs"], floor_step(sb["months_cap"] * M / W), floor_step(sb["phi"] * l_star / sb["delta"])
        )
        if "sandbox_mult" in kn:
            w_sandbox = floor_step(w_sandbox * kn["sandbox_mult"])
    c.t(
        "satellites.sandbox",
        {"level": L, "W": W, "M": M, "l_star": l_star, "knowledge": knowledge},
        w_sandbox,
        "satellites.sandbox",
    )

    th = S["theme_tech"]
    phi_t = Y["biases"]["familiarite"]["theme_phi"] if "familiarite" in biases else th["phi"]
    tech = floor_step(e_cap / 100 * th["s_ref"] + phi_t * l_star / th["delta"])
    c.t(
        "satellites.theme_tech",
        {"e_cap_pct": e_cap, "s_ref": th["s_ref"], "phi": phi_t, "l_star": l_star},
        tech,
        "satellites.theme_tech",
    )

    # ---- composition
    Cm = Y["composition"]
    e_cap_f = e_cap / 100
    etf_eq = round(max(0.10, 0.6 * e_cap_f), 4)
    etf_bd = round(ceil_step(0.65 * (1 - e_min / 100), 0.05), 4)
    cash_max = 1.0 if L == "N0" else round(0.5 * (1 - e_min / 100), 4)
    cash_min = Y["levels"][L].get("cash_like_min")
    c.t(
        "composition",
        {"level": L, "e_cap_pct": e_cap, "e_min_pct": e_min},
        {
            "etf_equity_each_max": etf_eq,
            "etf_bond_each_max": etf_bd,
            "cash_like_max": cash_max,
            "cash_like_min": cash_min,
            "long_duration_max": Cm["long_duration_max"][L],
            "gold_max": Cm["gold_max"][L],
        },
        "composition",
    )
    bud = _budgets(L, e_cap, c)
    cdar_on = "aversion_perte" in biases or (
        p.composure is not None and p.composure.value < Y["tolerance"]["low_composure_cdar"]["threshold"]
    )

    # ---- limites (1:1 avec limits_template)
    values: dict[str, tuple[float | None, float | None, str]] = {
        "alloc.growth": (e_min / 100, e_cap_f, f"{c.src(f'levels.{L}.equity')} ; {c.src('dollar_rule.e_cap')}"),
        "alloc.cash_like": (
            cash_min,
            cash_max,
            c.src("composition.cash_like_max") + (f" ; {c.src('levels.N0.cash_like_min')}" if cash_min else ""),
        ),
        "alloc.long_duration": (None, Cm["long_duration_max"][L], c.src(f"composition.long_duration_max.{L}")),
        "alloc.gold": (None, Cm["gold_max"][L], c.src(f"composition.gold_max.{L}")),
        "alloc.crypto": (None, w_crypto, crypto_src),
        "conc.etf_equity_each": (None, etf_eq, c.src("composition.etf_equity_each_max")),
        "conc.etf_bond_each": (None, etf_bd, c.src("composition.etf_bond_each_max")),
        "conc.single_each": (None, w_single, single_src),
        "conc.single_total": (
            None,
            w_single_total,
            c.src("satellites.single_name.total_phi") if w_single_total else single_src.split(" ; ")[0],
        ),
        "exp.tech": (
            None,
            tech,
            c.src("satellites.theme_tech")
            + (f" ; {c.src('biases.familiarite.theme_phi')}" if "familiarite" in biases else ""),
        ),
        "risk.cvar_m": (
            None,
            round(bud["cvar_m"][0] - w_crypto * cr["cvar_m_proxy"], 6),
            bud["cvar_m"][1] + (f" ; {c.src('satellites.crypto.cvar_m_proxy')}" if w_crypto else ""),
        ),
        "risk.cvar_12m": (None, bud["cvar_12m"][0], bud["cvar_12m"][1]),
        "risk.mdd": (None, bud["mdd"][0], bud["mdd"][1]),
        "risk.vol": (None, bud["vol"][0], bud["vol"][1]),
        "risk.cdar_m": (None, bud["cvar_m"][0], f"{c.src('biases.aversion_perte')} ; {bud['cvar_m'][1]}"),
        "risk.stress_2022": (None, bud["s2022"][0], bud["s2022"][1]),
    }
    limits: list[Limit] = []
    for t in Y["limits_template"]:
        rid = t["rule_id"]
        if rid == "sat.sandbox":
            continue  # emise seulement avec une demande (RequestView.limits)
        if rid == "risk.cdar_m" and not cdar_on:
            continue
        lo, hi, src = values[rid]
        derived = t["derived_from"]
        if rid == "risk.cdar_m":
            derived = "profile.biases[aversion_perte]" if "aversion_perte" in biases else "profile.composure<40"
        lim = Limit(
            rule_id=rid,
            kind=t["kind"],
            selector=Selector(**t["selector"]),
            min=lo,
            max=hi,
            blocking=t.get("blocking", True),
            derived_from=derived,
            source=src,
            description_fr=f"{rid} niveau {L}",
        )
        limits.append(lim)
        c.t(f"limit.{rid}", {"level": L}, {"min": lo, "max": hi}, src.split(" ; ")[0])

    # biais de familiarite : titre de l'employeur
    if "familiarite" in biases:
        emp = sorted(
            {e.ticker for e in p.employer_equity if e.ticker}
            | ({p.income.employer_ticker} if p.income and p.income.employer_ticker else set())
        )
        emp = [a for a in emp if a in uni]
        if emp:
            mult = Y["biases"]["familiarite"]["employer_ticker_cap_mult"]
            v = floor_step(w_single * mult)
            limits.append(
                Limit(
                    rule_id="bias.familiarite.employer",
                    kind="asset_weight",
                    selector=Selector(assets=emp),
                    max=v,
                    derived_from="profile.biases[familiarite] ; profile.employer_equity",
                    source=f"{c.src('biases.familiarite.employer_ticker_cap_mult')} ; {single_src}",
                    description_fr="titre de l'employeur plafonne",
                )
            )
            c.t(
                "biases.familiarite.employer",
                {"tickers": emp, "w_single": w_single, "mult": mult},
                v,
                "biases.familiarite.employer_ticker_cap_mult",
            )

    # ---- exclusions (contraintes legales bloquantes, filtres de valeurs)
    excluded: dict[str, str] = {}
    for lc in p.legal_constraints:
        if lc.blocking:
            for a in lc.tickers:
                if a in uni:
                    excluded[a] = f"profile.legal_constraints[{lc.kind}]"
    for vf in p.preferences.value_filters:
        for a, verdict in sorted(vf.per_ticker.items()):
            if a in uni and (verdict == "exclu" or (verdict == "zone_grise" and vf.decided_utc is None)):
                excluded.setdefault(a, f"profile.preferences.value_filters[{vf.rule}]={verdict}")
    if excluded:
        c.t("universe.excluded", {}, dict(sorted(excluded.items())), "profile")

    # ---- demande specifique
    rv = (
        _request_view(request, p, uni, excluded, classes, W, w_sandbox, w_single, w_crypto, biases, c)
        if request
        else None
    )
    if rv is not None:
        _request_limits = rv.limits

    # ---- emphase
    goals_h = [_goal_horizon(g, as_of) for g in p.goals]
    besoin_h = [_goal_horizon(g, as_of) for g in p.goals if g.priority.value == "besoin"]
    pos = [h.market_value for h in p.holdings] + [e.value or 0.0 for e in p.employer_equity]
    signals = {
        "min_goal_horizon_years": min(goals_h),
        "has_recurring_withdrawal": any(g.recurring_withdrawal for g in p.goals),
        "min_besoin_horizon_years": min(besoin_h) if besoin_h else None,
        "tolerance_gt_capacity": Tval > C or any("tolerance>capacit" in _norm(f) for f in p.consistency_flags),
        "max_loss_declared": l_decl is not None,
        "has_debt": bool(p.debts),
        "emergency_short": (p.emergency_fund_months or 0.0) < cap["emergency_required_months"],
        "emotional_bias": bool(biases & {"FOMO", "aversion_perte"})
        or any(b.kind.value == "emotionnel" for b in p.biases),
        "esg_required": p.preferences.esg_required,
        "has_value_filters": bool(p.preferences.value_filters),
        "has_tilts": bool(p.preferences.tilts),
        "max_position_share": (max(pos) / W) if pos and W else None,
        "has_legal_constraints": bool(p.legal_constraints),
        "has_employer_equity": bool(p.employer_equity),
        "has_user_rules": bool(p.user_rules),
        "request_outside_policy": rv.outside_policy if rv else False,
    }
    emphasis, fired, etrace = compute_emphasis(signals, emphasis_path)
    c.trace.extend(etrace)

    # ---- decision et PolicySpec
    if protection:
        kind = "protection"
    elif must_missing:
        kind = "incomplet"
    elif status == "INCOMPLETE":
        kind = "position_attente"
    else:
        kind = None
    c.t(
        "decision_kind", {"status": status, "protection": protection, "must_have_missing": must_missing}, kind, "status"
    )

    sig = _signature(p, as_of, request, Y, uni, questionnaire)
    policy = None
    if kind not in ("protection", "incomplet"):
        d = Y.get("policy_defaults") or {}
        ov = {
            a: {
                tag: ExposureOverride(value=v["value"], source=v["source"], status=v.get("status", "HYPOTHESE"))
                for tag, v in tags.items()
            }
            for a, tags in (Y.get("exposure_overrides") or {}).items()
            if a in uni
        }
        hp = {
            a: HistoryProxy(proxy=v["proxy"], source=v["source"])
            for a, v in (Y.get("history_proxies") or {}).items()
            if a in uni
        }
        lb = {a: float(v) for a, v in (Y.get("loss_bounds") or {}).items() if a in uni}
        policy = PolicySpec(
            policy_id=f"f1-{p.profile_id}-v{p.version}-{as_of.isoformat()}-{sig}",
            profile_id=p.profile_id,
            profile_version=p.version,
            created_utc=datetime.combine(as_of, time(0), tzinfo=UTC),
            currency="CAD",
            universe=uni,
            excluded=dict(sorted(excluded.items())),
            objective=d.get("objective", "min_risk"),
            risk_measure=d.get("risk_measure", "CVAR"),
            cvar_beta=d.get("cvar_beta", 0.95),
            lookback_months=d.get("lookback_months", 120),
            limits=limits,
            exposure_overrides=ov,
            history_proxies=hp,
            loss_bounds=lb,
            loss_bounds_source=(f"{c.src('loss_bounds')} : {Y.get('loss_bounds_source')}" if lb else None),
            missing_defaults=list(c.missing),
        )

    return CompileResult(
        policy=policy,
        level=L,
        R=R,
        capacity=cap,
        tolerance={
            "T": Tval,
            "person": tol["person"]["steps"],
            "candidates": [{"who": x["who"], "T": x["T"]} for x in tol["candidates"]],
        },
        decision_kind=kind,
        emphasis=emphasis,
        trace=c.trace,
        missing_defaults=list(c.missing),
        status=status,
        level_from_R=LV[iR],
        horizon_years=T,
        l_star=l_star,
        e_cap=e_cap_f,
        limits=limits,
        buckets=buckets,
        emphasis_rules=fired,
        request=rv,
        near_cutoff=near,
    )


def _request_view(
    req: SpecificRequest, p: InvestorProfile, uni, excluded, classes, W, w_sandbox, w_single, w_crypto, biases, c: _Ctx
) -> RequestView:
    a = req.ticker
    cls = classes.get(a)
    in_uni = a in uni
    req_w = req.weight if req.weight is not None else (req.amount_cad / W if W else None)
    req_cad = req.amount_cad if req.amount_cad is not None else (req.weight * W if W else None)
    caps = [w_sandbox]
    reasons = []
    single = w_single if cls == "equity_single" else None
    crypto = w_crypto if cls == "crypto" else None
    if single is not None:
        caps.append(single)
    if crypto is not None:
        caps.append(crypto)
    applicable = min(caps) if in_uni and a not in excluded else 0.0
    if not in_uni:
        reasons.append("ticker hors univers du mandat")
    if a in excluded:
        reasons.append(f"ticker exclu : {excluded[a]}")
    if req_w is None:
        reasons.append("poids de la demande inconnu (investable_wealth absent)")
    elif req_w > applicable + EPS:
        reasons.append(f"poids demande {req_w:.4f} > plafond applicable {applicable:.4f}")
    sb = c.Y["satellites"]["sandbox"]
    fomo = "FOMO" in biases
    cooldown = max(sb["cooldown_days"], c.Y["biases"]["FOMO"]["cooldown_days"] if fomo else 0)
    lims = []
    if in_uni and a not in excluded:
        lims.append(
            Limit(
                rule_id="sat.sandbox",
                kind="group_weight",
                selector=Selector(assets=[a]),
                max=w_sandbox,
                derived_from="profile.requests" + (" ; profile.biases[FOMO]" if fomo else ""),
                source=c.src("satellites.sandbox"),
                description_fr=f"bac a sable {a}",
            )
        )
    c.t(
        "request",
        {"ticker": a, "class": cls, "requested_weight": req_w},
        {"applicable_max": applicable, "outside_policy": bool(reasons)},
        "satellites.sandbox",
    )
    return RequestView(
        ticker=a,
        asset_class=cls,
        in_universe=in_uni,
        excluded_reason=excluded.get(a),
        requested_weight=req_w,
        requested_cad=req_cad,
        sandbox_max=w_sandbox,
        sandbox_max_cad=round(w_sandbox * W, 2) if W else None,
        single_name_max=single,
        crypto_max=crypto,
        applicable_max=applicable,
        applicable_max_cad=round(applicable * W, 2) if W else None,
        outside_policy=bool(reasons),
        reasons=reasons,
        sandbox_only=fomo,
        cooldown_days=cooldown,
        limits=lims,
    )
