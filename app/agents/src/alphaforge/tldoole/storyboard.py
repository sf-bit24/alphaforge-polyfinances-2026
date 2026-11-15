"""A8, ``explainVideo-Agent`` : le scénario d'une vidéo courte qui explique un concept à un investisseur.

A8 part des points clés validés du concept (catalogue) et demande ses chiffres aux outils de faits (code).
Son scénario passe par ``submit_storyboard``, qui le valide et renvoie les erreurs à corriger :

- structure : de 4 à 7 scènes, une accroche au début, « à retenir » à la fin, une idée par scène;
- chiffres : tout nombre d'une scène vient d'un fait que la scène cite (``fact`` ou ``cites``), des points
  clés du concept, ou d'un petit entier; le code affiche les valeurs du registre, jamais celles du modèle;
- cadre : expliquer, jamais conseiller (aucune recommandation d'achat ou de vente), longueur parlée bornée;
- un quiz d'une question vérifie la compréhension dans l'interface.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from strands import tool

from ..agentkit import AgentSpec, ModelFactory, run_agent, tool_result
from ..errors import AppError
from ..trace import Trace
from . import render
from .concepts import Concept, normalize
from .facts import FactBook, FactError, number_tokens

MIN_SCENES, MAX_SCENES = 4, 7
MAX_HEADLINE, MAX_BODY, MAX_LABEL, MAX_ITEM = 60, 150, 60, 80
MIN_NARRATION, MAX_NARRATION = 15, 260
# Polly (neural, fr-CA) dit environ 13 caractères par seconde : 950 caractères font environ 70 secondes.
MIN_TOTAL, MAX_TOTAL = 250, 950
DATA_LAYOUTS = ("number", "chart", "compare")
SMALL_NUMBERS = {str(n) for n in range(13)}
YEARS = {str(y) for y in range(1990, 2036)}

_ADVICE = re.compile(
    r"\b(je vous recommande|nous vous recommandons|je recommande|vous devriez (acheter|vendre|investir|placer)"
    r"|il faut (acheter|vendre)|achetez (des|du|de la|maintenant|ce|cette)|vendez (vos|tout|maintenant|ce|cette)"
    r"|you should (buy|sell|invest)|i recommend|we recommend|buy now|sell now|sell everything)\b"
)
DISCLAIMER = {
    "fr": "C'est une explication, pas un conseil financier.",
    "en": "This is an explanation, not financial advice.",
}


@dataclass
class StoryboardResult:
    storyboard: dict[str, Any]
    facts: FactBook


def key_point_numbers(concept: Concept, locale: str) -> set[str]:
    tokens: set[str] = set()
    for point in concept.points(locale):
        tokens |= number_tokens(point)
    return tokens


def system_prompt(locale: str) -> str:
    language = "French (Canada). Address the investor as 'vous'" if locale != "en" else "English"
    return (
        "You are A8, the explainer-video scriptwriter of AlphaForge AI, an educational investment simulation "
        "(no real transactions, no personalised advice). You write the script of ONE short vertical video "
        "(about 60 seconds once spoken, 950 characters of narration at most) that explains ONE concept to ONE "
        "investor who showed they do not understand it yet.\n"
        "Rules:\n"
        "1. Content: only the vetted key points of the concept, plus facts returned by the fact tools. Never "
        "state a number that does not come from a fact tool result or from the key points. A scene that says or "
        "shows a number must cite its fact: `fact` for number and chart and compare scenes, `cites` for others.\n"
        "2. Form: 4 to 7 scenes, one idea each. Start with a `hook` built on the investor's own question or "
        "situation (never repeat personal amounts), then explain, then show real data from the starter dataset "
        "(a `number`, `chart` or `compare` scene) when a fact tool is relevant, and end with an `outro` "
        "('to remember') listing 2 or 3 short takeaways.\n"
        "3. Words: headline at most 60 characters; narration at most 220 characters per scene (about 15 seconds), "
        "short sentences, plain words for the knowledge level, a concrete analogy for beginners. Write numbers in "
        "digits exactly as the fact tools format them.\n"
        "4. Explain, never advise: no buy, sell or hold recommendation, no product pick, no promise of returns; "
        "say that past results do not guarantee future results when you show past data.\n"
        "5. Add a quiz: one question that checks understanding of the concept (not of a number), 2 or 3 options, "
        "the index of the right answer and a one-sentence explanation.\n"
        f"6. Language: {language}.\n"
        "Call the fact tools you need first, then submit_storyboard. If it returns errors, fix them and submit "
        "again."
    )


def build_prompt(
    concept: Concept,
    *,
    locale: str,
    level: str,
    evidence: list[dict[str, Any]],
    has_portfolio: bool,
    simpler: bool,
    previous_headlines: list[str],
) -> str:
    context = {
        "concept": {
            "id": concept.id,
            "label": concept.text("label", locale),
            "suggested_title": concept.text("title", locale),
            "key_points": concept.points(locale),
            "fact_hints": list(concept.fact_hints),
        },
        "investor": {
            "locale": locale,
            "knowledge_level": level,
            "has_confirmed_portfolio": has_portfolio,
            "evidence": [
                {k: v for k, v in e.items() if k in ("kind", "quote", "field", "value", "rule")} for e in evidence
            ],
        },
        "layouts": {
            "hook": "headline (+ optional body): the question the video answers",
            "statement": "headline + body: one idea in words",
            "number": "headline + fact 'f<n>.<metric>' (+ optional label): one big number from a fact",
            "chart": "headline + fact 'f<n>' of a fact that has chart=true",
            "compare": "headline + fact 'f<n>' of a compare_assets fact (bars), or the client_portfolio fact",
            "list": "headline + 2 to 4 items",
            "outro": "headline + 2 or 3 items (takeaways)",
        },
    }
    if simpler:
        context["revision"] = {
            "why": "The investor watched a previous video on this concept and said it was still unclear.",
            "do": "Make it simpler: one analogy, fewer numbers, shorter sentences, different angle.",
            "previous_headlines": previous_headlines[:8],
        }
    return "<context>\n" + json.dumps(context, ensure_ascii=False, indent=1, default=str) + "\n</context>"


class StoryboardDraft:
    """Validation de ``submit_storyboard`` et construction du scénario normalisé."""

    def __init__(self, concept: Concept, facts: FactBook, *, locale: str, level: str):
        self.concept = concept
        self.facts = facts
        self.locale = locale
        self.level = level
        self.base_numbers = key_point_numbers(concept, locale) | SMALL_NUMBERS | YEARS
        self.result: dict[str, Any] | None = None

    # ------------------------------------------------------------------ validation
    def submit(self, title: Any, scenes: Any, quiz: Any) -> dict[str, Any]:
        errors: list[str] = []
        if not isinstance(title, str) or not title.strip() or len(title) > 70:
            errors.append("title is required, at most 70 characters")
        if not isinstance(scenes, list) or not MIN_SCENES <= len(scenes) <= MAX_SCENES:
            return {"status": "error", "errors": [f"scenes must be a list of {MIN_SCENES} to {MAX_SCENES} scenes"]}
        built: list[dict[str, Any]] = []
        for index, raw in enumerate(scenes, start=1):
            scene, scene_errors = self._scene(index, raw)
            errors.extend(scene_errors)
            if scene:
                built.append(scene)
        if built and built[0]["layout"] != "hook":
            errors.append("the first scene must use the hook layout")
        if built and built[-1]["layout"] != "outro":
            errors.append("the last scene must use the outro layout")
        if self.concept.fact_hints and not any(s["layout"] in DATA_LAYOUTS for s in built):
            errors.append("add one number, chart or compare scene built on a fact tool result")
        total = sum(len(s["narration"]) for s in built)
        if built and not MIN_TOTAL <= total <= MAX_TOTAL:
            errors.append(f"total narration is {total} characters; keep it between {MIN_TOTAL} and {MAX_TOTAL}")
        quiz_built, quiz_errors = self._quiz(quiz, built)
        errors.extend(quiz_errors)
        if errors:
            return {"status": "error", "errors": errors[:12]}
        disclaimer = DISCLAIMER.get(self.locale, DISCLAIMER["fr"])
        if not any(word in normalize(built[-1]["narration"]) for word in ("conseil", "advice")):
            built[-1]["narration"] = f"{built[-1]['narration'].rstrip()} {disclaimer}"
        facts_used = sorted({f for s in built for f in s["facts"]}, key=lambda f: int(f[1:]))
        self.result = {
            "concept_id": self.concept.id,
            "locale": self.locale,
            "level": self.level,
            "title": title.strip(),
            "scenes": built,
            "quiz": quiz_built,
            "facts_used": facts_used,
        }
        return {"status": "ok", "scenes": len(built), "narration_chars": total}

    def _scene(self, index: int, raw: Any) -> tuple[dict[str, Any] | None, list[str]]:
        where = f"scene {index}"
        if not isinstance(raw, dict):
            return None, [f"{where}: must be an object"]
        errors = []
        layout = raw.get("layout")
        if layout not in render.LAYOUTS:
            return None, [f"{where}: layout must be one of {', '.join(render.LAYOUTS)}"]
        headline = _text(raw.get("headline"))
        narration = _text(raw.get("narration"))
        body = _text(raw.get("body"))
        label = _text(raw.get("label"))
        items = [_text(i) for i in raw.get("items") or [] if _text(i)]
        if not headline or len(headline) > MAX_HEADLINE:
            errors.append(f"{where}: headline is required, at most {MAX_HEADLINE} characters")
        if not MIN_NARRATION <= len(narration) <= MAX_NARRATION:
            errors.append(f"{where}: narration must be {MIN_NARRATION} to {MAX_NARRATION} characters")
        if body and len(body) > MAX_BODY:
            errors.append(f"{where}: body must be at most {MAX_BODY} characters")
        if label and len(label) > MAX_LABEL:
            errors.append(f"{where}: label must be at most {MAX_LABEL} characters")
        if any(len(i) > MAX_ITEM for i in items):
            errors.append(f"{where}: each item must be at most {MAX_ITEM} characters")
        if layout == "statement" and not body:
            errors.append(f"{where}: a statement needs a body")
        if layout == "list" and not 2 <= len(items) <= 4:
            errors.append(f"{where}: a list needs 2 to 4 items")
        if layout == "outro" and not (2 <= len(items) <= 3 or (body and not items)):
            errors.append(f"{where}: an outro needs 2 or 3 items")

        fact_ids: list[str] = []
        fact_ref = raw.get("fact")
        if layout in DATA_LAYOUTS:
            error = self._check_data(layout, fact_ref)
            if error:
                errors.append(f"{where}: {error}")
            else:
                fact_ids.append(str(fact_ref).split(".")[0])
        for ref in raw.get("cites") or []:
            try:
                fact, _ = self.facts.resolve(str(ref).split(".")[0])
            except FactError as exc:
                errors.append(f"{where}: cites: {exc}")
                continue
            if fact["fact_id"] not in fact_ids:
                fact_ids.append(fact["fact_id"])

        allowed = self.base_numbers | self.facts.allowed_numbers(fact_ids)
        texts = [headline, narration, body, label, *items]
        stray = sorted({t for text in texts for t in number_tokens(text)} - allowed)
        if stray:
            errors.append(
                f"{where}: the numbers {', '.join(stray)} do not come from the facts this scene cites "
                f"({', '.join(fact_ids) or 'none'}); cite the fact (fact or cites) or remove them"
            )
        for text in texts:
            if text and _ADVICE.search(normalize(text)):
                errors.append(f"{where}: explain, do not advise (no buy or sell recommendation)")
                break
        if errors:
            return None, errors
        return {
            "layout": layout,
            "headline": headline,
            "body": body or None,
            "label": label or None,
            "items": items,
            "narration": narration,
            "fact": str(fact_ref) if layout in DATA_LAYOUTS else None,
            "facts": fact_ids,
        }, []

    def _check_data(self, layout: str, ref: Any) -> str | None:
        if not isinstance(ref, str):
            return f"a {layout} scene needs fact"
        try:
            fact, metric = self.facts.resolve(ref)
        except FactError as exc:
            return str(exc)
        if layout == "number" and metric is None:
            return "a number scene needs fact 'f<n>.<metric>'"
        if layout == "chart" and (metric is not None or self.facts.series(fact["fact_id"]) is None):
            return "a chart scene needs fact 'f<n>' of a fact with chart=true"
        if layout == "compare":
            if metric is not None:
                return "a compare scene needs fact 'f<n>' (no metric)"
            if fact["kind"] == "portfolio" and len(fact.get("top_positions") or []) < 2:
                return "the portfolio fact has fewer than 2 positions to compare"
            if fact["kind"] not in ("compare", "portfolio"):
                return "a compare scene needs a compare_assets fact or the client_portfolio fact"
        return None

    def _quiz(self, quiz: Any, scenes: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, list[str]]:
        if not isinstance(quiz, dict):
            return None, ["quiz is required: {question, options, answer, explanation}"]
        question = _text(quiz.get("question"))
        options = [_text(o) for o in quiz.get("options") or [] if _text(o)]
        explanation = _text(quiz.get("explanation"))
        errors = []
        if not question or len(question) > 140:
            errors.append("quiz.question is required, at most 140 characters")
        if not 2 <= len(options) <= 3 or any(len(o) > 70 for o in options):
            errors.append("quiz.options: 2 or 3 options of at most 70 characters")
        answer = quiz.get("answer")
        if not isinstance(answer, int) or isinstance(answer, bool) or not 0 <= answer < max(len(options), 1):
            errors.append("quiz.answer is the index of the right option")
        if not explanation or len(explanation) > 220:
            errors.append("quiz.explanation is required, at most 220 characters")
        all_facts = [f for s in scenes for f in s["facts"]]
        allowed = self.base_numbers | self.facts.allowed_numbers(all_facts)
        stray = sorted({t for text in [question, *options, explanation] for t in number_tokens(text)} - allowed)
        if stray:
            errors.append(f"quiz: the numbers {', '.join(stray)} do not come from the cited facts")
        if errors:
            return None, errors
        return {"question": question, "options": options, "answer": answer, "explanation": explanation}, []

    # ------------------------------------------------------------------ vers le rendu
    def render_scenes(self) -> list[render.Scene]:
        if self.result is None:
            raise ValueError("no storyboard")
        return [to_render_scene(scene, self.facts, self.locale) for scene in self.result["scenes"]]


def _text(value: Any) -> str:
    return re.sub(r"\s+", " ", value).strip() if isinstance(value, str) else ""


def source_line(facts: FactBook, fact_ids: list[str], locale: str) -> str | None:
    parts = []
    for fact_id in fact_ids:
        fact = facts.facts.get(fact_id)
        if not fact:
            continue
        source = fact.get("source") or {}
        text = str(source.get("title") or "")
        period = fact.get("period")
        if period:
            text += f", {period['start']} \u2013 {period['end']}"
        if fact.get("assumption"):
            text += f". {fact['assumption']}"
        if text and text not in parts:
            parts.append(text)
    if not parts:
        return None
    prefix = "Source : " if locale != "en" else "Source: "
    return prefix + " · ".join(parts)


def bar_label(item: dict[str, Any]) -> str:
    """« Shopify (SHOP.TO) » si le nom est court, sinon le symbole seul."""
    name, entity = str(item.get("name") or ""), str(item.get("entity") or "")
    label = f"{name} ({entity})" if name and name != entity else entity
    return label if len(label) <= 30 else entity


def to_render_scene(scene: dict[str, Any], facts: FactBook, locale: str) -> render.Scene:
    out = render.Scene(
        layout=scene["layout"],
        headline=scene["headline"],
        body=scene.get("body"),
        items=list(scene.get("items") or []),
        source=source_line(facts, scene["facts"], locale),
    )
    ref = scene.get("fact")
    if scene["layout"] == "number" and ref:
        fact, metric = facts.resolve(ref)
        label = scene.get("label") or f"{metric.get('label', '')} · {fact.get('entity', '')}".strip(" ·")
        sublabel = None
        if ref.endswith(".max_drawdown") and "drawdown_peak" in fact.get("metrics", {}):
            m = fact["metrics"]
            sublabel = f"{m['drawdown_peak']['text']} \u2013 {m['drawdown_trough']['text']}"
        elif fact.get("period"):
            sublabel = f"{fact['period']['start']} \u2013 {fact['period']['end']}"
        out.number = {"text": metric["text"], "label": label, "sublabel": sublabel}
    elif scene["layout"] == "chart" and ref:
        out.chart = dict(facts.series(ref.split(".")[0]) or {})
    elif scene["layout"] == "compare" and ref:
        fact, _ = facts.resolve(ref.split(".")[0])
        if fact["kind"] == "compare":
            out.bars = [{"label": bar_label(i), "value": i["value"], "text": i["text"]} for i in fact["items"]]
            out.body = out.body or fact.get("label")
        else:
            out.bars = list(fact.get("top_positions") or [])
    return out


def write_storyboard(
    concept: Concept,
    *,
    locale: str,
    level: str,
    evidence: list[dict[str, Any]],
    facts: FactBook,
    has_portfolio: bool,
    simpler: bool,
    previous_headlines: list[str],
    model_factory: ModelFactory,
    model_id: str,
    trace: Trace,
    kb_search: Any | None = None,
) -> StoryboardResult:
    draft = StoryboardDraft(concept, facts, locale=locale, level=level)

    def fact_call(fn, *args) -> str:
        try:
            return tool_result(facts.public(fn(*args)))
        except FactError as exc:
            return tool_result({"status": "error", "reason": str(exc)})

    @tool(
        name="asset_stats",
        description=(
            "Facts for one ticker of the starter dataset (adjusted daily prices 2021-11 to 2026-11): total_return, "
            "cagr, annualized_volatility, max_drawdown with peak, trough and recovery months, value_of_100; chart=true."
        ),
        inputSchema={"json": {"type": "object", "properties": {"ticker": {"type": "string"}}, "required": ["ticker"]}},
    )
    def asset_stats(ticker: str) -> str:
        return fact_call(facts.asset_stats, ticker)

    @tool(
        name="compare_assets",
        description=(
            "Compare 2 or 3 tickers of the starter dataset on one metric (total_return, cagr, annualized_volatility, "
            "max_drawdown, value_of_100). Returns bars for a compare scene and the ratio of the first to the last."
        ),
        inputSchema={
            "json": {
                "type": "object",
                "properties": {
                    "tickers": {"type": "array", "items": {"type": "string"}, "minItems": 2, "maxItems": 3},
                    "metric": {"type": "string"},
                },
                "required": ["tickers", "metric"],
            }
        },
    )
    def compare_assets(tickers: list[str], metric: str) -> str:
        return fact_call(facts.compare_assets, tickers, metric)

    @tool(
        name="macro_series",
        description=(
            "First, last, min and max of a macro series of the starter dataset, with dates; chart=true. Series: "
            "V39079 (Bank of Canada policy rate), BD.CDN.2YR.DQ.YLD and BD.CDN.10YR.DQ.YLD (Canada bond yields), "
            "STATIC_TOTALCPICHANGE (Canada CPI y/y), DFF, DGS2, DGS10, CPIAUCSL, UNRATE (United States)."
        ),
        inputSchema={
            "json": {"type": "object", "properties": {"series_id": {"type": "string"}}, "required": ["series_id"]}
        },
    )
    def macro_series(series_id: str) -> str:
        return fact_call(facts.macro_series, series_id)

    @tool(
        name="fx_usdcad",
        description="USD/CAD exchange rate facts 2021-11 to 2026-11 (Bank of Canada); chart=true.",
        inputSchema={"json": {"type": "object", "properties": {}}},
    )
    def fx_usdcad() -> str:
        return fact_call(facts.fx_usdcad)

    @tool(
        name="compound_growth",
        description=(
            "Illustrative compound growth with a constant assumed yearly return (the assumption is shown on screen). "
            "Bounds: initial_cad 0..10,000,000, monthly_cad 0..100,000, annual_rate_pct -10..15, years 1..50."
        ),
        inputSchema={
            "json": {
                "type": "object",
                "properties": {
                    "initial_cad": {"type": "number"},
                    "monthly_cad": {"type": "number"},
                    "annual_rate_pct": {"type": "number"},
                    "years": {"type": "integer"},
                },
                "required": ["initial_cad", "monthly_cad", "annual_rate_pct", "years"],
            }
        },
    )
    def compound_growth(initial_cad: float, monthly_cad: float, annual_rate_pct: float, years: int) -> str:
        return fact_call(facts.compound_growth, initial_cad, monthly_cad, annual_rate_pct, years)

    @tool(
        name="fee_drag",
        description=(
            "Illustrative effect of yearly fees on a lump sum with a constant assumed return. Bounds: amount_cad "
            "100..10,000,000, annual_return_pct -5..15, fee_pct 0..5, years 1..50."
        ),
        inputSchema={
            "json": {
                "type": "object",
                "properties": {
                    "amount_cad": {"type": "number"},
                    "annual_return_pct": {"type": "number"},
                    "fee_pct": {"type": "number"},
                    "years": {"type": "integer"},
                },
                "required": ["amount_cad", "annual_return_pct", "fee_pct", "years"],
            }
        },
    )
    def fee_drag(amount_cad: float, annual_return_pct: float, fee_pct: float, years: int) -> str:
        return fact_call(facts.fee_drag, amount_cad, annual_return_pct, fee_pct, years)

    @tool(
        name="client_portfolio",
        description=(
            "Facts from the investor's confirmed existing portfolio (weights computed by code): total value, number "
            "of positions, weight of the largest position, share in CAD, share listed in Canada, top positions."
        ),
        inputSchema={"json": {"type": "object", "properties": {}}},
    )
    def client_portfolio() -> str:
        return fact_call(facts.client_portfolio)

    @tool(
        name="search_general_knowledge",
        description=(
            "Search the general knowledge base (methodology notes, collected news) for a short excerpt. Returns an "
            "empty list when it is not available."
        ),
        inputSchema={"json": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
    )
    def search_general_knowledge(query: str) -> str:
        if kb_search is None or not getattr(kb_search, "enabled", False):
            return tool_result({"results": [], "note": "knowledge base not available"})
        return tool_result({"results": kb_search.search(query)})

    scene_schema = {
        "type": "object",
        "properties": {
            "layout": {"type": "string", "enum": list(render.LAYOUTS)},
            "headline": {"type": "string"},
            "body": {"type": "string"},
            "fact": {"type": "string"},
            "label": {"type": "string"},
            "items": {"type": "array", "items": {"type": "string"}},
            "cites": {"type": "array", "items": {"type": "string"}},
            "narration": {"type": "string"},
        },
        "required": ["layout", "headline", "narration"],
    }

    @tool(
        name="submit_storyboard",
        description=(
            "Submit the video script: title, 4 to 7 scenes (layout, headline, narration, and body, fact, label, "
            "items or cites depending on the layout) and quiz {question, options, answer, explanation}. Returns the "
            "errors to fix, if any."
        ),
        inputSchema={
            "json": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "scenes": {"type": "array", "items": scene_schema, "minItems": MIN_SCENES, "maxItems": MAX_SCENES},
                    "quiz": {
                        "type": "object",
                        "properties": {
                            "question": {"type": "string"},
                            "options": {"type": "array", "items": {"type": "string"}},
                            "answer": {"type": "integer"},
                            "explanation": {"type": "string"},
                        },
                        "required": ["question", "options", "answer", "explanation"],
                    },
                },
                "required": ["title", "scenes", "quiz"],
            }
        },
        context=True,
    )
    def submit_storyboard(title: str, scenes: list[dict[str, Any]], quiz: dict[str, Any], tool_context) -> str:
        outcome = draft.submit(title, scenes, quiz)
        if outcome.get("status") == "ok":
            tool_context.agent.cancel(after_current_tools=True)
        return tool_result(outcome)

    tools = [asset_stats, compare_assets, macro_series, fx_usdcad, compound_growth, fee_drag, submit_storyboard]
    if has_portfolio:
        tools.insert(-1, client_portfolio)
    if kb_search is not None and getattr(kb_search, "enabled", False):
        tools.insert(-1, search_general_knowledge)
    spec = AgentSpec(
        actor="A8",
        name="explainVideo-Agent",
        effort="medium",
        system_prompt=system_prompt(locale),
        tools=tools,
        max_turns=12,
        max_tokens=8000,
        tool_summaries={
            "submit_storyboard": lambda i: {
                "title": i.get("title"),
                "layouts": [s.get("layout") for s in i.get("scenes") or [] if isinstance(s, dict)],
            }
        },
    )
    prompt = build_prompt(
        concept,
        locale=locale,
        level=level,
        evidence=evidence,
        has_portfolio=has_portfolio,
        simpler=simpler,
        previous_headlines=previous_headlines,
    )
    run = run_agent(spec, prompt, model_factory=model_factory, model_id=model_id, trace=trace)
    if draft.result is None:
        run.follow_up(
            "You did not submit a valid storyboard. Fix the errors and call submit_storyboard now.", trace, max_turns=4
        )
    if draft.result is None:
        raise AppError(
            "model_error", trace.t("A8 n'a pas rendu de scénario valide.", "A8 returned no valid storyboard.")
        )
    storyboard = dict(draft.result)
    storyboard["sources"] = _sources(facts, storyboard["facts_used"])
    storyboard["render"] = draft.render_scenes()
    return StoryboardResult(storyboard=storyboard, facts=facts)


def _sources(facts: FactBook, fact_ids: list[str]) -> list[dict[str, Any]]:
    seen, out = set(), []
    for fact_id in fact_ids:
        source = (facts.facts.get(fact_id) or {}).get("source")
        if source and source.get("id") not in seen:
            seen.add(source.get("id"))
            out.append(dict(source))
    return out
