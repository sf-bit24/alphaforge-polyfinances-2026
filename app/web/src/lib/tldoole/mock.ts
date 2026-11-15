/**
 * In-memory simulator of the `tldoole` runtime (AGENT_MODE=mock): the same envelopes and shapes as
 * CONTRACTS.md 8, without AWS. Videos have no file; the UI shows their status and their "why".
 */
import type { Feed, TldooleRequest, VideoCard } from "./types";

interface MockState {
  videos: VideoCard[];
  gaps: Feed["gaps"];
}

const CATALOG = [
  { concept_id: "fnb", label: "FNB", title: "Un FNB, c'est quoi ?" },
  { concept_id: "diversification", label: "Diversification", title: "Diversifier, vraiment ?" },
  { concept_id: "volatilite", label: "Volatilité", title: "La volatilité, en clair" },
  { concept_id: "baisse_maximale", label: "Baisse maximale", title: "La pire baisse" },
  { concept_id: "horizon", label: "Horizon", title: "Votre horizon de placement" },
  { concept_id: "celi_reer", label: "CELI et REER", title: "CELI ou REER ?" },
  { concept_id: "frais", label: "Frais", title: "Les frais qui s'additionnent" },
  { concept_id: "interets_composes", label: "Intérêts composés", title: "L'effet boule de neige" },
];

const globalForMock = globalThis as unknown as { __alphaforgeTldooleMock?: Map<string, MockState> };
const states: Map<string, MockState> = (globalForMock.__alphaforgeTldooleMock ??= new Map());

const now = () => new Date().toISOString();
const hex = () => Math.floor(Math.random() * 0xffff).toString(16).padStart(4, "0");
const stamp = () => now().replace(/[-:]/g, "").slice(0, 15).toLowerCase();

function video(conceptId: string, status: VideoCard["status"], reason: string, why: VideoCard["why"]): VideoCard {
  const concept = CATALOG.find((c) => c.concept_id === conceptId) ?? CATALOG[0]!;
  return {
    video_id: `v${stamp()}-${concept.concept_id}-${hex()}`,
    concept_id: concept.concept_id,
    label: concept.label,
    title: concept.title,
    status,
    level: "beginner",
    locale: "fr",
    reason,
    version: 1,
    created_at: now(),
    updated_at: now(),
    duration_ms: status === "ready" ? 64000 : null,
    why,
    quiz:
      status === "ready"
        ? { question: "Que recevez-vous en achetant une part d'un FNB ?", options: ["Une seule action", "Un petit morceau de tout le panier"] }
        : null,
    sources: [
      { id: "starter-prices-daily", title: "Jeu de départ, prix quotidiens ajustés (Yahoo Finance)", resource: "starter:prices_daily.csv" },
    ],
    feedback: null,
    error: null,
    video_url: null,
    poster_url: null,
    captions_url: null,
  };
}

function state(clientId: string): MockState {
  let current = states.get(clientId);
  if (!current) {
    const ready = video("fnb", "ready", "detected", [
      { kind: "message", quote: "Je ne comprends pas trop c'est quoi un FNB.", provenance: "a1:1", at: now() },
    ]);
    const queued = video("volatilite", "rendering", "detected", [
      { kind: "answer", field: "risk_tolerance.drop_reaction", value: "sell_all", provenance: "base:q_drop_reaction", at: now() },
    ]);
    current = {
      videos: [queued, ready],
      gaps: [
        { concept_id: "fnb", label: "FNB", status: "video", confidence: 0.9, reason: "Vous avez demandé ce qu'est un FNB.", detector: "A7", video_id: ready.video_id, detected_at: now() },
        { concept_id: "volatilite", label: "Volatilité", status: "video", confidence: 0.65, reason: "Vous acceptez de fortes variations, mais vendriez tout à la première baisse.", detector: "A7", video_id: queued.video_id, detected_at: now() },
      ],
    };
    states.set(clientId, current);
  }
  // La vidéo en montage devient prête après quelques secondes, comme le ferait MediaConvert.
  for (const item of current.videos) {
    if (item.status !== "ready" && item.status !== "failed" && Date.now() - Date.parse(item.created_at ?? now()) > 12000) {
      item.status = "ready";
      item.duration_ms = 58000;
      item.quiz = { question: "La volatilité mesure…", options: ["Seulement les baisses", "L'ampleur des variations, à la hausse comme à la baisse"] };
    }
  }
  return current;
}

const ok = (body: Record<string, unknown>) => ({ status: 200, body: { ok: true, release: "mock", ...body } });

export function mockTldoole(request: TldooleRequest): { status: number; body: unknown } {
  const current = state(request.client_id);
  if (request.action === "feed") {
    return ok({
      client_id: request.client_id,
      locale: "fr",
      videos: current.videos,
      gaps: current.gaps,
      pending: current.videos.filter((v) => ["queued", "scripting", "rendering"].includes(v.status)).length,
      catalog: CATALOG,
    });
  }
  if (request.action === "request") {
    const active = current.videos.find((v) => v.concept_id === request.concept_id && ["queued", "scripting", "rendering"].includes(v.status));
    if (active) return ok({ client_id: request.client_id, video: active, created: false });
    const created = video(request.concept_id, "queued", "request", [{ kind: "request", provenance: "tldoole:request", at: now() }]);
    current.videos.unshift(created);
    return ok({ client_id: request.client_id, video: created, created: true });
  }
  const target = current.videos.find((v) => v.video_id === request.video_id);
  if (!target) return { status: 200, body: { ok: false, release: "mock", error: { code: "not_found", message: "Vidéo introuvable." } } };
  const correct = request.quiz_answer === undefined ? null : request.quiz_answer === 1;
  const verdict = request.verdict ?? (correct ? "understood" : "unclear");
  target.feedback = { verdict, quiz_answer: request.quiz_answer ?? null, correct };
  let followUp: VideoCard | null = null;
  if (verdict === "unclear" && !current.videos.some((v) => v.concept_id === target.concept_id && v.status !== "ready")) {
    followUp = { ...video(target.concept_id, "queued", "feedback", target.why), version: target.version + 1 };
    current.videos.unshift(followUp);
  }
  return ok({
    client_id: request.client_id,
    video: target,
    quiz: correct === null ? null : { correct, answer: 1, explanation: "Une part donne un petit morceau de tout ce que contient le panier." },
    follow_up: followUp,
  });
}
