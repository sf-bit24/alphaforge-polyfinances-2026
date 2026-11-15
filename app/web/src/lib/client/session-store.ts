/**
 * Client session of the profile flow: the client_id kept in localStorage, the last
 * ClientState, the trace of every request, and the A1 conversation. It is a plain
 * external store (subscribe / getSnapshot) consumed with useSyncExternalStore.
 */
import type { AnswerValue, ClientState, KnowledgeLevel, Locale, Question, Stage, TraceStep } from "@/lib/contract/schemas";
import type { PositionInput, UploadFile } from "@/lib/contract/requests";
import { ClientState as ClientStateSchema } from "@/lib/contract/schemas";
import { callAgent, callAgentStream, toApiError, type ApiError, type StreamHandlers } from "./api";
import { clearSessionStorage, readClientId, readHistory, writeClientId, writeHistory } from "./session-storage";

export interface TraceRun {
  id: string;
  action: string;
  startedAt: string;
  durationMs: number | null;
  status: "running" | "ok" | "error";
  streamed: boolean;
  steps: TraceStep[];
  error: { code: string; message: string } | null;
}

export interface AnsweredItem {
  question_id: string;
  prompt: string;
  display: string;
}

export type ConversationEntry =
  | { id: string; role: "agent"; at: string; message: string | null; questions: Question[]; stage: Stage; runId?: string }
  | { id: string; role: "user"; at: string; answers: AnsweredItem[]; message: string | null; stop: boolean };

export interface SessionSnapshot {
  hydrated: boolean;
  clientId: string | null;
  state: ClientState | null;
  resuming: boolean;
  pending: string | null;
  error: ApiError | null;
  errorAction: string | null;
  notice: "not_found" | null;
  streamText: string;
  liveRun: TraceRun | null;
  runs: TraceRun[];
  conversation: ConversationEntry[];
  /** Increments after every successful request, so dependent views can refresh. */
  revision: number;
}

export interface ErrorMessages {
  network: string;
  invalidResponse: string;
  noResult: string;
}

const MAX_RUNS = 40;
const MAX_ENTRIES = 120;

const INITIAL: SessionSnapshot = {
  hydrated: false,
  clientId: null,
  state: null,
  resuming: false,
  pending: null,
  error: null,
  errorAction: null,
  notice: null,
  streamText: "",
  liveRun: null,
  runs: [],
  conversation: [],
  revision: 0,
};

function uid(): string {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}

interface RequestOptions {
  streamed: boolean;
  /** A new session: runs, state and conversation start empty. */
  fresh?: boolean;
  /** A request whose answer has no trace step leaves no run. */
  quiet?: boolean;
  /** Shown at once; dropped if the request fails. */
  userEntry?: ConversationEntry | null;
  /** Adds A1's answer to the conversation when it says something. */
  agentEntry?: boolean;
}

/** A request in flight: what it calls, how it shows, and the trace run that records it. */
interface PendingRequest {
  action: string;
  call: (handlers: StreamHandlers) => Promise<ClientState>;
  options: RequestOptions;
  run: TraceRun;
  started: number;
}

function newRun(action: string, { streamed }: Pick<RequestOptions, "streamed">): TraceRun {
  return { id: uid(), action, startedAt: new Date().toISOString(), durationMs: null, status: "running", streamed, steps: [], error: null };
}

/** Newest first, at most MAX_RUNS. */
function withNewRun(runs: TraceRun[], run: TraceRun): TraceRun[] {
  return [run, ...runs].slice(0, MAX_RUNS);
}

/** A1's message and questions in a ClientState, as a conversation entry. */
function agentEntryOf(state: ClientState): Extract<ConversationEntry, { role: "agent" }> {
  return { id: uid(), role: "agent", at: new Date().toISOString(), message: state.message, questions: state.questions, stage: state.stage };
}

export interface ReplyInput {
  answers?: Array<{ question_id: string; value: AnswerValue; prompt: string; display: string }>;
  message?: string;
  stop?: boolean;
}

export class SessionStore {
  private snapshot: SessionSnapshot = INITIAL;
  private readonly listeners = new Set<() => void>();
  private locale: Locale = "fr";
  private messages: ErrorMessages = { network: "Network error", invalidResponse: "Invalid response", noResult: "No result" };
  private initialized = false;
  private retryLast: (() => Promise<boolean>) | null = null;

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  getSnapshot = (): SessionSnapshot => this.snapshot;

  getServerSnapshot = (): SessionSnapshot => INITIAL;

  /** The latest ClientState, for code that just awaited an action (render code reads the snapshot instead). */
  getState = (): ClientState | null => this.snapshot.state;

  configure(locale: Locale, messages: ErrorMessages): void {
    this.locale = locale;
    this.messages = messages;
  }

  private set(patch: Partial<SessionSnapshot>): void {
    this.snapshot = { ...this.snapshot, ...patch };
    for (const listener of this.listeners) listener();
  }

  private persist(): void {
    const { clientId, runs, conversation } = this.snapshot;
    if (!clientId) return;
    writeHistory(clientId, runs.slice(0, MAX_RUNS), conversation.slice(-MAX_ENTRIES));
  }

  private options() {
    return { locale: this.locale, messages: this.messages };
  }

  /** Read localStorage once, then resume the stored session if any. */
  init = async (): Promise<void> => {
    if (this.initialized) return;
    this.initialized = true;
    const clientId = readClientId();
    if (!clientId) {
      this.set({ hydrated: true });
      return;
    }
    this.set({
      hydrated: true,
      clientId,
      resuming: true,
      ...readHistory(clientId),
    });
    await this.resume();
  };

  resume = async (): Promise<boolean> => {
    const clientId = this.snapshot.clientId;
    if (!clientId) return false;
    const ok = await this.execute(
      "session.resume",
      () => callAgent({ action: "session.resume", client_id: clientId, locale: this.locale }, ClientStateSchema, this.options()),
      { streamed: false },
    );
    if (!ok && this.snapshot.error?.code === "not_found") {
      clearSessionStorage(clientId);
      this.set({ ...INITIAL, hydrated: true, notice: "not_found" });
    } else {
      this.seedConversation();
    }
    this.set({ resuming: false });
    return ok;
  };

  start = async (): Promise<boolean> => {
    const ok = await this.execute(
      "session.start",
      () => callAgent({ action: "session.start", locale: this.locale }, ClientStateSchema, this.options()),
      { streamed: false, fresh: true },
    );
    if (ok) this.set({ notice: null });
    return ok;
  };

  restart = async (): Promise<boolean> => {
    this.forget();
    return this.start();
  };

  forget = (): void => {
    const clientId = this.snapshot.clientId;
    if (clientId) clearSessionStorage(clientId);
    this.retryLast = null;
    this.set({ ...INITIAL, hydrated: true });
  };

  answerBase = (questionId: string, value: AnswerValue): Promise<boolean> => {
    const clientId = this.requireClient();
    return this.execute(
      "base.answer",
      () => callAgent({ action: "base.answer", client_id: clientId, question_id: questionId, value }, ClientStateSchema, this.options()),
      { streamed: false },
    );
  };

  /**
   * « Passer les questions » (tests, demos): answers every pending base question with
   * `answerFor`, one `base.answer` each as if clicked, and skips the existing portfolio if
   * the runtime asks for it. Stops at the first failure, whose error stays on the session.
   */
  answerAllBase = async (answerFor: (question: Question) => AnswerValue, onAnswered?: (count: number) => void): Promise<boolean> => {
    let count = 0;
    // Bounded: the questionnaire has about 30 questions, branches included.
    for (let guard = 0; guard < 80; guard += 1) {
      const state = this.snapshot.state;
      if (!state) return false;
      if (state.stage === "existing_portfolio") return this.skipPortfolio();
      const question = state.stage === "base_questions" ? state.questions[0] : undefined;
      if (!question) return true;
      if (!(await this.answerBase(question.id, answerFor(question)))) return false;
      count += 1;
      onAnswered?.(count);
    }
    return false;
  };

  submitPortfolio = (input: { text?: string; files?: UploadFile[] }): Promise<boolean> => {
    const clientId = this.requireClient();
    return this.execute(
      "portfolio.submit",
      (handlers) =>
        callAgentStream(
          {
            action: "portfolio.submit",
            client_id: clientId,
            ...(input.text?.trim() ? { text: input.text } : {}),
            ...(input.files?.length ? { files: input.files } : {}),
          },
          handlers,
          this.options(),
        ),
      { streamed: true },
    );
  };

  confirmPortfolio = (positions: PositionInput[]): Promise<boolean> => {
    const clientId = this.requireClient();
    return this.execute(
      "portfolio.confirm",
      () => callAgent({ action: "portfolio.confirm", client_id: clientId, positions }, ClientStateSchema, this.options()),
      { streamed: false },
    );
  };

  skipPortfolio = (): Promise<boolean> => {
    const clientId = this.requireClient();
    return this.execute(
      "portfolio.skip",
      () => callAgent({ action: "portfolio.skip", client_id: clientId }, ClientStateSchema, this.options()),
      { streamed: false },
    );
  };

  /** `followup.reply`; with no answer and no message, A1 asks its first follow-ups. */
  reply = (input: ReplyInput): Promise<boolean> => {
    const clientId = this.requireClient();
    const answers = input.answers ?? [];
    const message = input.message?.trim() ?? "";
    const userEntry: ConversationEntry | null =
      answers.length > 0 || message || input.stop
        ? {
            id: uid(),
            role: "user",
            at: new Date().toISOString(),
            answers: answers.map(({ question_id, prompt, display }) => ({ question_id, prompt, display })),
            message: message || null,
            stop: Boolean(input.stop),
          }
        : null;
    return this.execute(
      "followup.reply",
      (handlers) =>
        callAgentStream(
          {
            action: "followup.reply",
            client_id: clientId,
            ...(answers.length ? { answers: answers.map(({ question_id, value }) => ({ question_id, value })) } : {}),
            ...(message ? { message } : {}),
            ...(input.stop ? { stop: true } : {}),
          },
          handlers,
          this.options(),
        ),
      { streamed: true, userEntry, agentEntry: true },
    );
  };

  updateSettings = (input: { locale?: Locale; knowledge_level?: KnowledgeLevel }): Promise<boolean> => {
    const clientId = this.requireClient();
    return this.execute(
      "settings.update",
      () => callAgent({ action: "settings.update", client_id: clientId, ...input }, ClientStateSchema, this.options()),
      { streamed: false, quiet: true },
    );
  };

  refreshProfile = (): Promise<boolean> => {
    const clientId = this.requireClient();
    return this.execute(
      "profile.get",
      () => callAgent({ action: "profile.get", client_id: clientId }, ClientStateSchema, this.options()),
      { streamed: false, quiet: true },
    );
  };

  retry = async (): Promise<boolean> => {
    const again = this.retryLast;
    if (!again) return false;
    return again();
  };

  dismissError = (): void => {
    this.set({ error: null, errorAction: null });
  };

  clearRuns = (): void => {
    this.set({ runs: [] });
    this.persist();
  };

  private requireClient(): string {
    const clientId = this.snapshot.clientId;
    if (!clientId) throw new Error("No client session");
    return clientId;
  }

  /** On resume into the follow-ups, show A1's pending message and questions. */
  private seedConversation(): void {
    const state = this.snapshot.state;
    if (!state || this.snapshot.conversation.length > 0) return;
    if ((state.stage === "followups" || state.stage === "complete") && (state.message || state.questions.length > 0)) {
      this.set({ conversation: [agentEntryOf(state)] });
      this.persist();
    }
  }

  private async execute(
    action: string,
    call: (handlers: StreamHandlers) => Promise<ClientState>,
    options: RequestOptions,
  ): Promise<boolean> {
    if (this.snapshot.pending) return false;
    const request: PendingRequest = { action, call, options, run: newRun(action, options), started: performance.now() };
    this.beginRequest(request);
    try {
      const result = await call(this.streamHandlers());
      this.completeRequest(request, result);
      return true;
    } catch (error) {
      this.failRequest(request, toApiError(error));
      return false;
    }
  }

  private beginRequest({ action, options, run }: PendingRequest): void {
    const conversationBefore = options.fresh ? [] : this.snapshot.conversation;
    this.set({
      pending: action,
      error: null,
      errorAction: null,
      liveRun: run,
      streamText: "",
      conversation: options.userEntry ? [...conversationBefore, options.userEntry] : conversationBefore,
      ...(options.fresh ? { runs: [], state: null } : {}),
    });
  }

  private streamHandlers(): StreamHandlers {
    return {
      onTrace: (step) => {
        const live = this.snapshot.liveRun;
        if (live) this.set({ liveRun: { ...live, steps: [...live.steps, step] } });
      },
      // One `delta` per agent message, carrying the whole message (CONTRACTS.md 3.4): replace, never append.
      onDelta: (text) => this.set({ streamText: text }),
    };
  }

  private completeRequest({ options, run, started }: PendingRequest, result: ClientState): void {
    const finished: TraceRun = { ...run, status: "ok", steps: result.trace, durationMs: performance.now() - started };
    // `message` is null after a deterministic transition: nothing to show then.
    const agentSpoke = Boolean(result.message) || result.questions.length > 0;
    const conversation =
      options.agentEntry && agentSpoke
        ? [
            ...this.snapshot.conversation,
            // Links the message to the trace of the request that produced it.
            { ...agentEntryOf(result), runId: finished.id },
          ]
        : this.snapshot.conversation;
    if (options.fresh || this.snapshot.clientId !== result.client_id) writeClientId(result.client_id);
    this.retryLast = null;
    this.set({
      clientId: result.client_id,
      state: result,
      pending: null,
      liveRun: null,
      streamText: "",
      runs: options.quiet && result.trace.length === 0 ? this.snapshot.runs : withNewRun(this.snapshot.runs, finished),
      conversation,
      revision: this.snapshot.revision + 1,
    });
    this.persist();
  }

  private failRequest({ action, call, options, run, started }: PendingRequest, apiError: ApiError): void {
    const failed: TraceRun = {
      ...run,
      status: "error",
      steps: this.snapshot.liveRun?.steps ?? [],
      durationMs: performance.now() - started,
      error: { code: apiError.code, message: apiError.message },
    };
    this.retryLast = () => this.execute(action, call, options);
    this.set({
      pending: null,
      liveRun: null,
      streamText: "",
      error: apiError,
      errorAction: action,
      runs: withNewRun(this.snapshot.runs, failed),
      // The optimistic user entry is dropped: the composer keeps the text for a retry.
      conversation: options.userEntry
        ? this.snapshot.conversation.filter((entry) => entry.id !== options.userEntry?.id)
        : this.snapshot.conversation,
    });
    this.persist();
  }
}
