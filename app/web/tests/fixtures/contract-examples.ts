/** The JSON examples of app/CONTRACTS.md, copied verbatim (placeholders filled where the contract uses "..."). */

export const question = {
  id: "q_horizon",
  source: "deterministic",
  dimension: "horizon",
  kind: "single_choice",
  prompt: "Dans combien de temps aurez-vous besoin d'une part importante de cet argent ?",
  help: "L'horizon ne se déduit ni de l'âge ni de la tolérance au risque.",
  options: [
    { value: "lt3", label: "Moins de 3 ans" },
    { value: "3to10", label: "De 3 à 10 ans" },
    { value: "gt10", label: "10 ans et plus" },
  ],
  min: null,
  max: null,
  unit: null,
  required: true,
  field: "horizon_band",
};

export const completeness = {
  score: 0.62,
  displayed: 0.62,
  threshold: 0.7,
  cap: 0.95,
  ready: false,
  missing: [{ dimension: "risk_capacity", field: "emergency_fund", label: "Fonds d'urgence" }],
};

export const profileView = {
  knowledge_level: "intermediate",
  effective_risk: "medium",
  dimensions: {
    objective: { status: "known", summary: "Croissance à long terme", fields: { goal: "growth" } },
    horizon: { status: "partial", summary: "10 ans et plus", fields: { horizon_band: "gt10" } },
    risk_tolerance: { status: "known", summary: "Élevée", fields: {} },
    risk_capacity: { status: "missing", summary: null, fields: {} },
    constraints: { status: "partial", summary: "CELI", fields: {} },
    preferences: { status: "known", summary: "Exclut le tabac", fields: {} },
    context: { status: "partial", summary: null, fields: {} },
  },
  risk: { tolerance: "high", capacity: "medium", effective: "medium" },
  facts: [{ field: "horizon.horizon_band", value: "gt10", provenance: "base:q_horizon", at: "2026-11-14T23:10:00Z" }],
  documents: [{ key: "clients/8f0c…/profil.md", title: "Profil investisseur" }],
};

export const portfolioView = {
  positions: [
    {
      id: "p1",
      raw: "100 RY.TO",
      ticker: "RY.TO",
      name: "Royal Bank of Canada",
      asset_class: "equity",
      sector: "Financials",
      market: "TSX",
      currency: "CAD",
      quantity: 100,
      market_value: null,
      account_type: "tfsa",
      price: 134.2,
      price_date: "2026-11-12",
      price_source: "starter:prices_daily.csv",
      value_cad: 13420.0,
      resolved: true,
      notes: null,
    },
  ],
  unresolved: [{ raw: "fonds maison XYZ", reason: "titre introuvable", position_id: "p2" }],
  fx: { pair: "USDCAD", rate: 1.4255, date: "2026-11-12", source: "starter:fx_usdcad_daily.csv" },
  exposures: {
    total_value_cad: 13420.0,
    by_asset_class: { equity: 1.0 },
    by_currency: { CAD: 1.0 },
    by_market: { TSX: 1.0 },
    by_sector: { Financials: 1.0 },
    top_positions: [{ id: "p1", weight: 1.0 }],
    flags: ["concentration_single_position", "home_bias_canada"],
  },
  status: "draft",
  sources: [
    { id: "starter-prices", title: "Jeu de départ, prices_daily.csv", resource: "starter:prices_daily.csv", retrieved_at: "2026-11-13" },
  ],
};

export const traceStep = {
  id: "st_01",
  at: "2026-11-14T23:10:00.120Z",
  kind: "deterministic",
  actor: "questionnaire",
  title: "Question suivante choisie par les règles",
  detail: "q_horizon après q_goal",
  inputs: { question_id: "q_goal" },
  outputs: { next: "q_horizon" },
  sources: [],
  duration_ms: 3,
};

export const clientState = {
  ok: true,
  release: "1a2b3c4d",
  client_id: "8f0c3a8e-5d7b-4e2a-9f51-2c6d3b1a7e90",
  locale: "fr",
  stage: "base_questions",
  message: null,
  questions: [question],
  profile: profileView,
  completeness,
  portfolio: null,
  trace: [traceStep],
};

export const errorEnvelope = {
  ok: false,
  release: "1a2b3c4d",
  error: { code: "invalid_answer", message: "texte lisible", details: {} },
};

export const health = { ok: true, role: "profile", release: "1a2b3c4d", env: "sandbox" };

/** Output of the collection state machine, state "Termine" of infrastructure/infra/stepfunctions.tf. */
export const collectionOutput = {
  run_id: "3f6c1a9e-2b4d-4c8a-9e1f-7a6b5c4d3e2f",
  collected: {
    press: {
      status: "ok",
      role: "press",
      run_id: "3f6c1a9e-2b4d-4c8a-9e1f-7a6b5c4d3e2f",
      items: 12,
      keys: ["staging/3f6c1a9e-2b4d-4c8a-9e1f-7a6b5c4d3e2f/press/a.json"],
      error: null,
      started_at: "2026-11-14T06:00:01Z",
      finished_at: "2026-11-14T06:04:00Z",
    },
    data: { status: "error", role: "data", error: { Error: "BedrockAgentCore.ValidationException", Cause: "run_id refusé" } },
  },
  curated: {
    status: "ok",
    role: "supervisor",
    run_id: "3f6c1a9e-2b4d-4c8a-9e1f-7a6b5c4d3e2f",
    written: ["general/actualites/2026/11/taux.md"],
    rejected: [{ key: "staging/3f6c1a9e-2b4d-4c8a-9e1f-7a6b5c4d3e2f/press/b.json", reason: "sans date de publication" }],
    error: null,
    started_at: "2026-11-14T06:05:00Z",
    finished_at: "2026-11-14T06:07:00Z",
  },
  ingestion: { job_id: "ABCDEFGHIJ", status: "COMPLETE", statistics: { numberOfDocumentsScanned: 9 } },
};
