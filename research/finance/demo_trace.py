"""Démo de traçabilité de bout en bout (mandat GÉNÉRIQUE, simulation seulement).

    ALPHAFORGE_LLM_MODE=record python research/finance/demo_trace.py

Une trace OpenTelemetry couvre : vérification d'entrée (Guardrail) → optimisation (F2) → contrôle du
Judge (F4) → alternative encadrée → explication LLM rejouable → vérification de sortie (nombres +
ancrage) → Decision validée → journal d'audit chaîné (local + S3 + DynamoDB).
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "app" / "agents" / "tests" / "finance"))

from alphaforge.finance.observability import (flush, log_event, record_decision, setup, span, verify_chain,  # noqa: E402
                           verify_decision, verify_input, verify_output)
from alphaforge.finance.contracts import Decision  # noqa: E402
from alphaforge.finance.llm import FileStore, LLMRequest, llm_call  # noqa: E402
from alphaforge.finance.portfolio import check, framed_alternative  # noqa: E402
from test_portfolio import AS_OF, policy  # noqa: E402

INFRA = json.loads((HERE / "infra" / "outputs.json").read_text())
GUARDRAIL = (INFRA["guardrail_id"], INFRA["guardrail_version"])


class Phrase(BaseModel):
    text_fr: str = Field(description="Une phrase en français simple")
    fact_ids: list[str] = Field(description="Identifiants exacts des faits dont viennent les nombres de la phrase")


class Explication(BaseModel):
    why: list[Phrase]
    limits: list[Phrase]


def main() -> None:
    setup(trace_file=str(HERE / "traces" / "demo.jsonl"), xray=True)
    os.environ.setdefault("ALPHAFORGE_LOG_FILE", str(HERE / "traces" / "app.jsonl"))
    os.environ.setdefault("ALPHAFORGE_CLOUDWATCH_LOGS", "1")
    p = policy()
    request_text = "Je veux mettre 50 % de mon portefeuille dans NVDA, tout le monde en parle."
    request = {"NVDA": 0.5, "SPY": 0.3, "ZST.TO": 0.2}

    with span("decision.pipeline", profile_id="demo", policy_id=p.policy_id, as_of=AS_OF) as root:
        gin = verify_input(request_text, GUARDRAIL)
        rep = check(request, p, AS_OF, trace_id="judge-demande")
        alt, rep_alt, method = framed_alternative(request, p, AS_OF)

        facts = list(rep.facts) + [f for f in rep_alt.facts if f.fact_id not in {x.fact_id for x in rep.facts}]
        key_facts = [f for f in facts if any(s in f.fact_id for s in ("max_titre[NVDA]", "cvar_max", "mdd_max"))]
        brief = {f.fact_id: {"libelle": f.label_fr, "valeur": f.value, "unite": f.unit} for f in key_facts}
        req = LLMRequest(
            model_id="us.anthropic.claude-haiku-5-5", effort="low", max_tokens=2000, output_model=Explication,
            node_id="explicateur", round=0, data_version=rep.trace.data_version, policy_version=p.policy_id,
            guardrail=GUARDRAIL,
            system=("Tu expliques une décision de simulation (jamais un conseil). Tu ne calcules rien : chaque "
                    "nombre que tu écris vient d'un fait fourni, avec le même arrondi, et tu cites son fact_id."),
            messages=({"role": "user", "content": [{"text":
                f"Demande : {gin.text_out}\nVerdict du Judge : {rep.verdict}.\nFaits : {json.dumps(brief, ensure_ascii=False)}\n"
                "Explique en 2 phrases pourquoi la demande est refusée, et en 1 phrase une limite de l'analyse."}]},))
        exp = llm_call(req, FileStore(HERE / "llm_records")).parsed

        text = " ".join(ph.text_fr for ph in exp.why)
        nums, gout = verify_output(text, key_facts, "Pourquoi la demande est-elle refusée ?", GUARDRAIL)

        to_st = lambda phs: [{"text_fr": ph.text_fr, "fact_ids": ph.fact_ids} for ph in phs]
        decision = Decision(
            decision_id=f"demo-{uuid.uuid4().hex[:8]}", profile_id="demo", profile_version=1,
            created_utc=datetime.now(timezone.utc), kind="refus_encadre", facts=facts,
            constraints=list(rep.checks), positions=[],
            explanation={"data_used": [{"text_fr": "Rendements mensuels CAD de l'engine, fenêtre de 120 mois.",
                                        "fact_ids": []}],
                         "why": to_st(exp.why), "limits": to_st(exp.limits),
                         "what_would_change": [{"text_fr": f"Alternative encadrée : {method}.", "fact_ids": []}]},
            trace=[rep.trace, rep_alt.trace])
        vd = verify_decision(decision)
        entry = record_decision(decision, str(HERE / "traces" / "journal"), aws=INFRA)
        root.set_attribute("alphaforge.decision_id", decision.decision_id)
        log_event("decision.done", decision_id=decision.decision_id, verdict=rep.verdict,
                  numbers_ok=nums.ok, faithful=vd.ok, grounding=gout.grounding)
        tid = f"{root.get_span_context().trace_id:032x}"

    flush()
    print(json.dumps({
        "trace_id": tid, "entree_guardrail": {"action": gin.action, "topics": gin.topics},
        "judge": {"verdict": rep.verdict, "bloquantes": list(rep.blocking_violations)},
        "alternative": {"methode": method, "verdict": rep_alt.verdict},
        "explication_rejouee": exp.model_dump(),
        "sortie": {"nombres_ok": nums.ok, "non_trouves": nums.unmatched, "ancrage": gout.grounding,
                   "pertinence": gout.relevance, "bloque": gout.blocked},
        "fidelite_par_phrase": vd.ok, "audit": {k: entry.get(k) for k in ("seq", "record_hash", "s3_key")},
        "chaine_intacte": verify_chain(str(HERE / "traces" / "journal"), "demo")[0],
    }, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
