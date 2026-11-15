"use client";

import { RefreshCw } from "lucide-react";
import { useEffect, useEffectEvent, useMemo, useRef, useState } from "react";
import type { BuildMode, DemoPersona, PortfolioBuildResponse } from "@/lib/contract/portfolio";
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

export function PortfolioView() {
  const { t, locale } = useI18n();
  const v = t.portfolioView;
  const { status: healthStatus, health } = useHealth(locale);
  const session = useSession();
  const mode = health?.mode ?? null;
  const mock = mode === "mock";
  const [picked, setPicked] = useState<Target>("amira");
  const [engine, setEngine] = useState<BuildMode>("rules");
  /** Builds asked for by the investor, per target and engine (a counter, so « Reconstruire » asks again). */
  const [requests, setRequests] = useState<Partial<Record<string, number>>>({});
  const [results, setResults] = useState<Partial<Record<string, BuildResult>>>({});
  const inflight = useRef(new Map<string, { nonce: number; controller: AbortController }>());

  const canSelf = !mock && mode !== null && session.clientId !== null;
  // « Mon profil » only exists with a client outside the simulator; fall back to the first persona.
  const target: Target = picked === "self" && !canSelf ? "amira" : picked;
  const used: BuildMode = mock ? "rules" : engine;
  const key = `${target}:${used}`;
  // The simulator answers at once from the engine's fixtures: it builds on selection. Elsewhere a build
  // costs runtime time (and model calls in llm mode), so it waits for the button.
  const wanted = requests[key] ?? (mock ? 0 : undefined);
  const result = results[key];
  const current: BuildState | undefined =
    wanted === undefined ? undefined : result && result.nonce === wanted ? result.state : { status: "loading" };

  const start = useEffectEvent((buildKey: string, nonce: number, forTarget: Target, forEngine: BuildMode) => {
    if (results[buildKey]?.nonce === nonce) return;
    const running = inflight.current.get(buildKey);
    if (running?.nonce === nonce) return;
    running?.controller.abort();
    const controller = new AbortController();
    inflight.current.set(buildKey, { nonce, controller });
    const scenario = forTarget === "self" ? null : DEMO_SCENARIOS[forTarget];
    const settle = (state: BuildResult["state"]) => {
      if (inflight.current.get(buildKey)?.controller !== controller) return;
      inflight.current.delete(buildKey);
      setResults((previous) => ({ ...previous, [buildKey]: { nonce, state } }));
    };
    buildPortfolio(
      {
        ...(scenario ? { persona: scenario.persona, ...(scenario.request ? { request: scenario.request } : {}) } : { client_id: session.clientId ?? undefined }),
        mode: forEngine,
        locale,
      },
      { locale, signal: controller.signal, messages: { network: t.errors.network, invalidResponse: t.errors.invalidResponse, noResult: t.errors.noResult } },
    ).then(
      (response) => settle({ status: "done", response }),
      (error: unknown) => {
        if (isAbort(error)) return;
        settle({
          status: "error",
          error: error instanceof ApiError ? error : { code: "network_error", message: error instanceof Error ? error.message : String(error), details: undefined },
        });
      },
    );
  });

  useEffect(() => {
    if (wanted !== undefined) start(key, wanted, target, used);
  }, [key, wanted, target, used]);

  useEffect(() => {
    const pending = inflight.current;
    return () => pending.forEach(({ controller }) => controller.abort());
  }, []);

  const ask = () => setRequests((previous) => ({ ...previous, [key]: (previous[key] ?? (mock ? 0 : -1)) + 1 }));

  const targets: Target[] = canSelf ? [...DEMO_PERSONAS, "self"] : [...DEMO_PERSONAS];
  const isFiction = target !== "self";

  return (
    <div className={d.page} style={{ display: "flex", flexDirection: "column" }}>
      <div className={d.main} style={{ width: "100%", flex: 1 }}>
        <div className={d.head}>
          <div>
            <h1>{v.title}</h1>
            <p>{v.lead}</p>
          </div>
        </div>

        <fieldset className={p.picker}>
          <legend>{v.personas.legend}</legend>
          {targets.map((item) => {
            const copy = v.personas[item];
            const request = item === "self" ? undefined : DEMO_SCENARIOS[item].request;
            return (
              <label key={item} className={p.persona}>
                <input type="radio" name="portfolio-target" value={item} checked={target === item} onChange={() => setPicked(item)} />
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

        {mode !== null && !mock ? (
          <div className={p.toolbar}>
            <label>
              {v.engine.label}
              <select className={p.select} value={engine} onChange={(event) => setEngine(event.target.value as BuildMode)}>
                <option value="rules">{v.engine.rules}</option>
                <option value="llm">{v.engine.llm}</option>
              </select>
            </label>
            <button
              type="button"
              className={cn(d.btn, p.primary)}
              disabled={current?.status === "loading"}
              onClick={ask}
            >
              {current?.status === "done" ? <RefreshCw aria-hidden className="size-4" /> : null}
              {current?.status === "done" ? v.rebuild : v.build}
            </button>
          </div>
        ) : null}

        {healthStatus === "idle" || healthStatus === "loading" ? (
          <div className={p.status}>
            <Spinner label={t.common.loading} />
          </div>
        ) : current === undefined ? (
          <div className={p.status}>
            <p>{mock ? t.common.loading : v.idle}</p>
          </div>
        ) : current.status === "loading" ? (
          <div className={p.status} aria-live="polite">
            <Spinner label={v.building} />
            {used === "llm" ? <p className={p.sub}>{v.buildingLlm}</p> : null}
          </div>
        ) : current.status === "error" ? (
          <ErrorNotice error={current.error} onRetry={ask} />
        ) : (
          <Loaded key={key} response={current.response} fixture={mock} />
        )}
      </div>
      <div className={p.banner} role="note">
        {isFiction ? <span className={p.fiction}>{v.fiction}</span> : null}
        <span>{v.banner}</span>
      </div>
    </div>
  );
}
