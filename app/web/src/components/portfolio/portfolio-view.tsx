"use client";

import { RefreshCw } from "lucide-react";
import { useEffect, useEffectEvent, useMemo, useRef, useState } from "react";
import type { BuildMode, DemoPersona, PortfolioBuildRequestInput, PortfolioBuildResponse } from "@/lib/contract/portfolio";
import type { Locale } from "@/lib/contract/schemas";
import { ApiError, buildPortfolio, isAbort } from "@/lib/client/api";
import { useHealth } from "@/lib/client/health";
import { useSession } from "@/lib/client/session";
import { useI18n } from "@/lib/i18n/provider";
import { indexFacts, indexTrace } from "@/lib/portfolio/decision";
import { formatCad } from "@/lib/portfolio/format";
import { DEMO_PERSONAS, DEMO_SCENARIOS } from "@/lib/portfolio/personas";
import d from "@/components/details/details.module.css";
import { cn } from "@/components/ui/cn";
import { Drawer } from "@/components/ui/drawer";
import { ErrorNotice } from "@/components/ui/error-notice";
import { Spinner } from "@/components/ui/spinner";
import { DecisionView } from "./decision-view";
import { DecisionProvider, FactPanel, type DecisionLookup } from "./facts";
import p from "./portfolio.module.css";

/** A demo persona (FICTION), or the investor's own profile (`client_id`) outside the simulator. */
type Target = DemoPersona | "self";

type BuildState =
  | { status: "loading" }
  | { status: "done"; response: PortfolioBuildResponse }
  | { status: "error"; error: Pick<ApiError, "code" | "message" | "details"> };

interface BuildResult {
  nonce: number;
  state: Exclude<BuildState, { status: "loading" }>;
}

type HealthStatus = ReturnType<typeof useHealth>["status"];

function Loaded({ response, fixture }: { response: PortfolioBuildResponse; fixture: boolean }) {
  const { t } = useI18n();
  const [panel, setPanel] = useState<{ ids: readonly string[]; title: string } | null>(null);
  const lookup = useMemo<DecisionLookup>(
    () => ({
      facts: indexFacts(response.decision),
      trace: indexTrace(response.decision),
      open: (ids, title) => setPanel({ ids, title: title ?? t.portfolioView.fact.panel }),
    }),
    [response, t],
  );
  return (
    <DecisionProvider value={lookup}>
      <DecisionView response={response} fixture={fixture} />
      <p className={d.pageNote} style={{ padding: "12px 0 0" }}>
        {response.decision.disclaimer_fr}
      </p>
      <Drawer open={panel !== null} onClose={() => setPanel(null)} label={panel?.title ?? t.portfolioView.fact.panel}>
        {panel ? <FactPanel ids={panel.ids} title={panel.title} /> : null}
      </Drawer>
    </DecisionProvider>
  );
}

/** The body of `build`: a demo scenario as it is written, or the investor's own profile. */
function buildInput(target: Target, clientId: string | null, engine: BuildMode, locale: Locale): Omit<PortfolioBuildRequestInput, "action"> {
  const scenario = target === "self" ? null : DEMO_SCENARIOS[target];
  return {
    ...(scenario ? { persona: scenario.persona, ...(scenario.request ? { request: scenario.request } : {}) } : { client_id: clientId ?? undefined }),
    mode: engine,
    locale,
  };
}

/** A failed build as the error notice shows it; anything that is not an ApiError is a network error. */
function buildError(error: unknown): BuildResult["state"] {
  return {
    status: "error",
    error: error instanceof ApiError ? error : { code: "network_error", message: error instanceof Error ? error.message : String(error), details: undefined },
  };
}

/** What the screen shows for the build it wants: nothing asked yet, its result, or a build under way. */
function currentState(wanted: number | undefined, result: BuildResult | undefined): BuildState | undefined {
  if (wanted === undefined) return undefined;
  return result && result.nonce === wanted ? result.state : { status: "loading" };
}

interface BuildTarget {
  target: Target;
  /** The engine actually used (always `rules` in the simulator). */
  engine: BuildMode;
  mock: boolean;
  clientId: string | null;
}

/**
 * Builds per target and engine, and what to show for the current one. Each request (`ask`, or the
 * selection itself in the simulator) runs one build; a newer request for the same key aborts the older
 * one, and leaving the page aborts them all.
 */
function usePortfolioBuild({ target, engine, mock, clientId }: BuildTarget) {
  const { t, locale } = useI18n();
  /** Builds asked for by the investor, per target and engine (a counter, so « Reconstruire » asks again). */
  const [requests, setRequests] = useState<Partial<Record<string, number>>>({});
  const [results, setResults] = useState<Partial<Record<string, BuildResult>>>({});
  const inflight = useRef(new Map<string, { nonce: number; controller: AbortController }>());
  const key = `${target}:${engine}`;
  // The simulator answers at once from the engine's fixtures: it builds on selection. Elsewhere a build
  // costs runtime time (and model calls in llm mode), so it waits for the button.
  const wanted = requests[key] ?? (mock ? 0 : undefined);

  const start = useEffectEvent((buildKey: string, nonce: number, forTarget: Target, forEngine: BuildMode) => {
    if (results[buildKey]?.nonce === nonce) return;
    const running = inflight.current.get(buildKey);
    if (running?.nonce === nonce) return;
    running?.controller.abort();
    const controller = new AbortController();
    inflight.current.set(buildKey, { nonce, controller });
    const settle = (state: BuildResult["state"]) => {
      if (inflight.current.get(buildKey)?.controller !== controller) return;
      inflight.current.delete(buildKey);
      setResults((previous) => ({ ...previous, [buildKey]: { nonce, state } }));
    };
    buildPortfolio(buildInput(forTarget, clientId, forEngine, locale), {
      locale,
      signal: controller.signal,
      messages: { network: t.errors.network, invalidResponse: t.errors.invalidResponse, noResult: t.errors.noResult },
    }).then(
      (response) => settle({ status: "done", response }),
      (error: unknown) => {
        if (isAbort(error)) return;
        settle(buildError(error));
      },
    );
  });

  useEffect(() => {
    if (wanted !== undefined) start(key, wanted, target, engine);
  }, [key, wanted, target, engine]);

  useEffect(() => {
    const pending = inflight.current;
    return () => pending.forEach(({ controller }) => controller.abort());
  }, []);

  const ask = () => setRequests((previous) => ({ ...previous, [key]: (previous[key] ?? (mock ? 0 : -1)) + 1 }));
  return { key, current: currentState(wanted, results[key]), ask };
}

function PersonaPicker({ targets, target, onPick }: { targets: Target[]; target: Target; onPick: (target: Target) => void }) {
  const { t } = useI18n();
  const v = t.portfolioView;
  return (
    <fieldset className={p.picker}>
      <legend>{v.personas.legend}</legend>
      {targets.map((item) => {
        const copy = v.personas[item];
        const request = item === "self" ? undefined : DEMO_SCENARIOS[item].request;
        return (
          <label key={item} className={p.persona}>
            <input type="radio" name="portfolio-target" value={item} checked={target === item} onChange={() => onPick(item)} />
            <span className={p.personaTop}>
              <span className={p.personaName}>{copy.name}</span>
              {item !== "self" ? (
                <span className={p.fiction} title={v.fictionHelp}>
                  {v.fiction}
                </span>
              ) : null}
            </span>
            <span className={p.personaLine}>{copy.tagline}</span>
            {request?.amount_cad !== undefined ? <span className={p.personaLine}>{v.request(formatCad(request.amount_cad), request.ticker)}</span> : null}
          </label>
        );
      })}
    </fieldset>
  );
}

interface ToolbarProps {
  engine: BuildMode;
  onEngine: (engine: BuildMode) => void;
  status: BuildState["status"] | undefined;
  onBuild: () => void;
}

/** The engine to build with and the build button, outside the simulator. */
function BuildToolbar({ engine, onEngine, status, onBuild }: ToolbarProps) {
  const { t } = useI18n();
  const v = t.portfolioView;
  return (
    <div className={p.toolbar}>
      <label>
        {v.engine.label}
        <select className={p.select} value={engine} onChange={(event) => onEngine(event.target.value as BuildMode)}>
          <option value="rules">{v.engine.rules}</option>
          <option value="llm">{v.engine.llm}</option>
        </select>
      </label>
      <button type="button" className={cn(d.btn, p.primary)} disabled={status === "loading"} onClick={onBuild}>
        {status === "done" ? <RefreshCw aria-hidden className="size-4" /> : null}
        {status === "done" ? v.rebuild : v.build}
      </button>
    </div>
  );
}

interface BuildStatusProps {
  health: HealthStatus;
  build: ReturnType<typeof usePortfolioBuild>;
  mock: boolean;
  engine: BuildMode;
}

/** The gateway's health first, then the build: not asked yet, under way, failed, or the decision. */
function BuildStatus({ health, build, mock, engine }: BuildStatusProps) {
  const { t } = useI18n();
  const v = t.portfolioView;
  const current = build.current;
  if (health === "idle" || health === "loading") {
    return (
      <div className={p.status}>
        <Spinner label={t.common.loading} />
      </div>
    );
  }
  if (current === undefined) {
    return (
      <div className={p.status}>
        <p>{mock ? t.common.loading : v.idle}</p>
      </div>
    );
  }
  if (current.status === "loading") {
    return (
      <div className={p.status} aria-live="polite">
        <Spinner label={v.building} />
        {engine === "llm" ? <p className={p.sub}>{v.buildingLlm}</p> : null}
      </div>
    );
  }
  if (current.status === "error") return <ErrorNotice error={current.error} onRetry={build.ask} />;
  return <Loaded key={build.key} response={current.response} fixture={mock} />;
}

export function PortfolioView() {
  const { t, locale } = useI18n();
  const v = t.portfolioView;
  const { status: healthStatus, health } = useHealth(locale);
  const session = useSession();
  const mode = health?.mode ?? null;
  const mock = mode === "mock";
  const [picked, setPicked] = useState<Target>("amira");
  const [engine, setEngine] = useState<BuildMode>("rules");
  const canSelf = !mock && mode !== null && session.clientId !== null;
  // « Mon profil » only exists with a client outside the simulator; fall back to the first persona.
  const target: Target = picked === "self" && !canSelf ? "amira" : picked;
  const used: BuildMode = mock ? "rules" : engine;
  const build = usePortfolioBuild({ target, engine: used, mock, clientId: session.clientId });
  const targets: Target[] = canSelf ? [...DEMO_PERSONAS, "self"] : [...DEMO_PERSONAS];

  return (
    <div className={d.page} style={{ display: "flex", flexDirection: "column" }}>
      <div className={d.main} style={{ width: "100%", flex: 1 }}>
        <div className={d.head}>
          <div>
            <h1>{v.title}</h1>
            <p>{v.lead}</p>
          </div>
        </div>
        <PersonaPicker targets={targets} target={target} onPick={setPicked} />
        {mode !== null && !mock ? <BuildToolbar engine={engine} onEngine={setEngine} status={build.current?.status} onBuild={build.ask} /> : null}
        <BuildStatus health={healthStatus} build={build} mock={mock} engine={used} />
      </div>
      <div className={p.banner} role="note">
        {target !== "self" ? <span className={p.fiction}>{v.fiction}</span> : null}
        <span>{v.banner}</span>
      </div>
    </div>
  );
}
