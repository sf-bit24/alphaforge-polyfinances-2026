"""Pont entre le magasin OKF de l'app (``alphaforge.store``, ``alphaforge.okf``, ``alphaforge.profile``)
et le volet portefeuille. Aucun second magasin : on lit ``clients/<id>/profil.md`` avec le code de
l'app, et on écrit la décision à côté, dans ``clients/<id>/decisions/``.

Clés écrites (proposition, à ajouter à app/CONTRACTS.md §5) :
    clients/<client_id>/decisions/<decision_id>.md      document OKF « Portfolio Decision » (résumé)
    clients/<client_id>/decisions/<decision_id>.json    Decision complète (Facts, contrôles, trace)
    clients/<client_id>/decisions/<decision_id>.policy.json   mandat (PolicySpec) appliqué
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from alphaforge import okf
from alphaforge.finance.contracts import Decision, InvestorProfile, PolicySpec
from alphaforge.finance.policy.from_profile_view import investor_profile_from_view
from alphaforge.profile.questionnaire import Questionnaire
from alphaforge.profile.state import ClientSession
from alphaforge.profile.views import completeness_view, profile_view
from alphaforge.store import Store


def decision_key(client_id: str, decision_id: str, ext: str = "md") -> str:
    return f"clients/{client_id}/decisions/{decision_id}.{ext}"


class OkfClientStore:
    """Lecture du profil et écriture de la décision via le magasin de l'app (S3 ou local)."""

    def __init__(self, store: Store, questionnaire: Questionnaire | None = None, locale: str = "fr"):
        self.store = store
        self.q = questionnaire or Questionnaire.load()
        self.locale = locale

    def view(self, client_id: str) -> tuple[dict[str, Any], dict[str, Any], ClientSession]:
        session = ClientSession.load(self.store, client_id)
        if session is None:
            raise KeyError(f"profil introuvable : {client_id}")
        return profile_view(self.q, session, self.locale), completeness_view(self.q, session, self.locale), session

    def load_profile(self, client_id: str) -> InvestorProfile:
        view, comp, session = self.view(client_id)
        return investor_profile_from_view(view, client_id, version=max(int(session.turn or 0), 1),
                                          created_utc=datetime.now(timezone.utc), completeness=comp)

    def save_decision(self, decision: Decision, policy: PolicySpec | None = None) -> str:
        cid, did = decision.profile_id, decision.decision_id
        self.store.put_json(decision_key(cid, did, "json"), decision.model_dump(mode="json"))
        if policy is not None:
            self.store.put_json(decision_key(cid, did, "policy.json"), policy.model_dump(mode="json"))
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        doc = okf.OkfDoc(frontmatter={
            "type": "Portfolio Decision", "title": f"Décision de portefeuille {did}",
            "description": "Proposition simulée du volet portefeuille, avec ses contrôles et son explication.",
            "tags": ["portefeuille", "decision"], "status": "draft", "owners": ["alphaforge-a3"],
            "sensitivity": "client", "generated": {"by": "agent:A3", "at": now},
            "sources": [{"id": "decision-json", "title": "Decision complète", "resource": decision_key(cid, did, "json")}],
            "data": {"kind": decision.kind, "simulation_only": True,
                     "positions": [{"asset_id": p.asset_id, "weight": round(p.weight, 6)} for p in decision.positions],
                     "n_facts": len(decision.facts), "n_checks": len(decision.constraints)},
        })
        body = "\n".join(f"- {s.text_fr}" for sec in (decision.explanation.data_used, decision.explanation.why,
                                                     decision.explanation.limits, decision.explanation.what_would_change)
                         for s in sec)
        doc.body = f"{decision.disclaimer_fr}\n\n{body}\n"
        key = decision_key(cid, did, "md")
        self.store.put_text(key, okf.render(doc))
        return key


class OkfMarketStore:
    """Preuves datées de la base générale. v1 : aucune preuve ESG structurée n'est encore publiée par
    A6, donc ``evidence`` renvoie une liste vide (les lentilles ne doivent jamais en inventer)."""

    def __init__(self, store: Store):
        self.store = store

    def evidence(self, ticker: str, topic: str, as_of) -> list:
        return []


def stores_from_env():
    """Construit les deux adaptateurs à partir de la configuration du runtime (S3 en AWS, local en dev)."""
    from alphaforge.config import Settings
    from alphaforge.store import make_store
    store = make_store(Settings.from_env())
    return OkfClientStore(store), OkfMarketStore(store)


def _dump(obj) -> str:  # utilitaire de débogage
    return json.dumps(obj, ensure_ascii=False, indent=1, default=str)
