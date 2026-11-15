"""Pont entre le magasin OKF de l'app (``alphaforge.store``, ``alphaforge.okf``, ``alphaforge.profile``)
et le volet portefeuille. Aucun second magasin : on lit ``clients/<id>/profil.md`` avec le code de
l'app, et on écrit la décision à côté, dans ``clients/<id>/decisions/``.

Clés écrites (proposition, à ajouter à app/CONTRACTS.md §5) :
    clients/<client_id>/decisions/<decision_id>.md      document OKF « Portfolio Decision » (résumé)
    clients/<client_id>/decisions/<decision_id>.json    Decision complète (Facts, contrôles, trace)
    clients/<client_id>/decisions/<decision_id>.policy.json   mandat (PolicySpec) appliqué

Clés lues de la base générale (``OkfMarketStore``, lot E) : ``general/societes/*.md`` (« Company Fundamentals ») et
``general/actualites/AAAA/MM/*.md`` (« News »).
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
from datetime import UTC, date, datetime
from typing import Any

from alphaforge import okf
from alphaforge.finance.contracts import Decision, Fact, InvestorProfile, PolicySpec
from alphaforge.finance.policy.from_profile_view import investor_profile_from_view
from alphaforge.finance.strategy.okf_facts import (
    FUNDAMENTALS_PREFIX,
    NEWS_PREFIX,
    CompanyFundamentals,
    NewsItem,
    OkfFactsError,
    WrongDocType,
    as_date,
    canonical_ticker,
    fundamentals_facts,
    news_fact,
    parse_company_fundamentals,
    parse_news,
)
from alphaforge.profile.questionnaire import Questionnaire
from alphaforge.profile.state import ClientSession
from alphaforge.profile.views import completeness_view, profile_view
from alphaforge.store import Store

log = logging.getLogger(__name__)
_NEWS_MONTH = re.compile(r"^general/actualites/(?P<y>\d{4})/(?P<m>\d{2})/")


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
        return investor_profile_from_view(
            view, client_id, version=max(int(session.turn or 0), 1), created_utc=datetime.now(UTC), completeness=comp
        )

    def save_decision(self, decision: Decision, policy: PolicySpec | None = None) -> str:
        cid, did = decision.profile_id, decision.decision_id
        self.store.put_json(decision_key(cid, did, "json"), decision.model_dump(mode="json"))
        if policy is not None:
            self.store.put_json(decision_key(cid, did, "policy.json"), policy.model_dump(mode="json"))
        now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        doc = okf.OkfDoc(
            frontmatter={
                "type": "Portfolio Decision",
                "title": f"Décision de portefeuille {did}",
                "description": "Proposition simulée du volet portefeuille, avec ses contrôles et son explication.",
                "tags": ["portefeuille", "decision"],
                "status": "draft",
                "owners": ["alphaforge-a3"],
                "sensitivity": "client",
                "generated": {"by": "agent:A3", "at": now},
                "sources": [
                    {"id": "decision-json", "title": "Decision complète", "resource": decision_key(cid, did, "json")}
                ],
                "data": {
                    "kind": decision.kind,
                    "simulation_only": True,
                    "positions": [{"asset_id": p.asset_id, "weight": round(p.weight, 6)} for p in decision.positions],
                    "n_facts": len(decision.facts),
                    "n_checks": len(decision.constraints),
                },
            }
        )
        body = "\n".join(
            f"- {s.text_fr}"
            for sec in (
                decision.explanation.data_used,
                decision.explanation.why,
                decision.explanation.limits,
                decision.explanation.what_would_change,
            )
            for s in sec
        )
        doc.body = f"{decision.disclaimer_fr}\n\n{body}\n"
        key = decision_key(cid, did, "md")
        self.store.put_text(key, okf.render(doc))
        return key


class OkfMarketStore:
    """Preuves datées de la base générale OKF (lot E), lues par le code, sans LLM et sans jamais deviner.

    Sujets de ``evidence(ticker, topic, as_of)`` :
    - ``fundamentals`` : documents « Company Fundamentals » de ``general/societes/`` dont ``data.ticker`` est le
      titre → Facts ``okf.fund.*`` publiés au plus tard à ``as_of`` (``finance.strategy.okf_facts``). Contexte
      cité par les lentilles seulement : poids nul dans le score de l'étape 0.
    - ``news`` : documents « News » de ``general/actualites/`` dont ``data.tickers`` contient le titre (casse et
      forme canoniques : ``shop.to`` → ``SHOP.TO``) → Facts ``okf.news.*``, toujours HYPOTHESE, les plus récents
      d'abord ; ``merge.apply_amendments`` refuse tout amendement qui s'en réclame, sauf ``flag_only``.
    - ``esg`` : aucune preuve ESG structurée n'est encore publiée par A6 → ``[]`` (crochet : ``_esg``).

    Une instance = un lot d'appels (une décision : ``app.py`` en crée une par invocation). Les listes et les
    documents sont lus une fois puis gardés en cache ; ``reset()`` force une relecture. ``inputs`` garde
    (clé → ETag) de chaque document de fondamentaux lu, pour la version des données (``data_version``) ; les
    actualités lues vont dans ``news_inputs`` et n'entrent JAMAIS dans cette version. Un document refusé est noté
    dans ``rejected`` (clé → raison) et ignoré ; une lecture impossible du magasin est notée dans ``inputs`` sous le
    préfixe, pour que la version des données le montre."""

    def __init__(self, store: Store, *, bucket: str | None = None, max_news: int = 5):
        self.store = store
        self.bucket = bucket if bucket is not None else getattr(store, "bucket", None)
        self.max_news = max_news
        self._lock = threading.RLock()
        self.reset()

    def reset(self) -> None:
        with self._lock:
            self.inputs: dict[str, str] = {}
            self.news_inputs: dict[str, str] = {}
            self.rejected: dict[str, str] = {}
            self._fundamentals: dict[str, CompanyFundamentals] | None = None
            self._news_keys: list[str] | None = None
            self._news: dict[str, NewsItem | None] = {}

    # ------------------------------------------------------------------ lecture
    def evidence(self, ticker: str, topic: str, as_of) -> list[Fact]:
        try:
            t = canonical_ticker(ticker)
        except OkfFactsError:
            return []  # un symbole mal formé (ex. donné par un LLM) n'est couvert par aucun document
        d = as_date(as_of)
        if topic == "fundamentals":
            cf = self.load_fundamentals().get(t)
            return fundamentals_facts(cf, d) if cf is not None else []
        if topic == "news":
            return self._news_facts(t, d)
        if topic == "esg":
            return self._esg(t, d)
        raise ValueError(f"sujet de preuve inconnu : {topic!r}")

    def _esg(self, ticker: str, as_of: date) -> list[Fact]:
        """Crochet ESG : brancher ici les preuves ESG structurées (exclusions d'indices, incidents, émissions) quand
        A6 en publiera, avec la même règle point dans le temps. D'ici là : rien, on n'invente aucune controverse."""
        return []

    def _unreadable(self, where: str, exc: Exception, sink: dict[str, str]) -> None:
        """Droits ou réseau : on le note (la version des données le montre), sans bloquer la décision."""
        log.warning("okf: lecture de %s impossible : %s", where, exc)
        sink[where] = f"erreur:{type(exc).__name__}"
        self.rejected[where] = f"lecture impossible : {type(exc).__name__}"

    def _read(self, key: str, sink: dict[str, str]) -> tuple[str, str] | None:
        try:
            obj = self.store.get(key)
        except Exception as exc:
            self._unreadable(key, exc, sink)
            return None
        if obj is None:
            return None
        tag = obj.etag.strip('"') or hashlib.sha256(obj.body).hexdigest()
        sink[key] = tag
        return tag, obj.text

    def _list(self, prefix: str, sink: dict[str, str]) -> list[str]:
        try:
            return sorted(i.key for i in self.store.list(prefix, limit=20000) if i.key.endswith(".md"))
        except Exception as exc:
            self._unreadable(prefix, exc, sink)
            return []

    def load_fundamentals(self) -> dict[str, CompanyFundamentals]:
        """Lit une fois tout ``general/societes/`` (clé → ETag dans ``inputs``) ; titre → document validé."""
        with self._lock:
            if self._fundamentals is not None:
                return self._fundamentals
            found: dict[str, CompanyFundamentals] = {}
            dup: set[str] = set()
            for key in self._list(FUNDAMENTALS_PREFIX, self.inputs):
                got = self._read(key, self.inputs)
                if got is None:
                    continue
                tag, text = got
                try:
                    cf = parse_company_fundamentals(text, key, tag, bucket=self.bucket)
                except WrongDocType:
                    self.inputs.pop(key, None)  # autre type de document (ex. un index) : pas un intrant
                    continue
                except OkfFactsError as exc:  # refusé, mais lu : sa correction changera la version des données
                    self.rejected[key] = str(exc)
                    log.warning("okf: %s", exc)
                    continue
                if cf.ticker in found or cf.ticker in dup:  # deux documents pour un titre : on ne choisit pas
                    other = found.pop(cf.ticker, None)
                    dup.add(cf.ticker)
                    for k in (key, other.key if other else None):
                        if k:
                            self.rejected[k] = f"{k} : plusieurs documents de fondamentaux pour {cf.ticker}"
                    continue
                found[cf.ticker] = cf
            self._fundamentals = found
            return found

    def _news_items(self, as_of: date) -> list[NewsItem]:
        with self._lock:
            if self._news_keys is None:
                self._news_keys = self._list(NEWS_PREFIX, self.news_inputs)
            out = []
            for key in self._news_keys:
                ym = _NEWS_MONTH.match(key)
                if ym and (int(ym["y"]), int(ym["m"])) > (as_of.year, as_of.month):
                    continue  # rangée sous son mois de publication : forcément publiée après as_of, pas lue
                if key not in self._news:
                    got = self._read(key, self.news_inputs)
                    item = None
                    if got is not None:
                        try:
                            item = parse_news(got[1], key, got[0])
                        except WrongDocType:
                            item = None
                        except OkfFactsError as exc:
                            self.rejected[key] = str(exc)
                    self._news[key] = item
                if self._news[key] is not None:
                    out.append(self._news[key])
            return out

    def _news_facts(self, ticker: str, as_of: date) -> list[Fact]:
        items = [i for i in self._news_items(as_of) if ticker in i.tickers and i.admissible(as_of)]
        items.sort(key=lambda i: (-i.published_at.timestamp(), i.key))  # les plus récentes d'abord
        return [news_fact(item, ticker, n) for n, item in enumerate(items[: self.max_news], start=1)]

    # ------------------------------------------------------------------ version des données
    def data_version(self, base: str | None) -> str:
        """``base`` + empreinte courte des (clé, ETag) des fondamentaux lus. Charge ``general/societes/`` d'abord :
        la version ne dépend donc pas des outils qu'un LLM a choisi d'appeler. Les actualités n'y entrent jamais."""
        self.load_fundamentals()
        with self._lock:
            digest = hashlib.sha256(json.dumps(sorted(self.inputs.items())).encode()).hexdigest()[:12]
        return f"{base}+okf:{digest}" if base else f"okf:{digest}"


def stores_from_env():
    """Construit les deux adaptateurs à partir de la configuration du runtime (S3 en AWS, local en dev)."""
    from alphaforge.config import Settings
    from alphaforge.store import make_store

    store = make_store(Settings.from_env())
    return OkfClientStore(store), OkfMarketStore(store)


def _dump(obj) -> str:  # utilitaire de débogage
    return json.dumps(obj, ensure_ascii=False, indent=1, default=str)
