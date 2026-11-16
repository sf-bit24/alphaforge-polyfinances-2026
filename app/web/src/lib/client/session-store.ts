/**
 * Client session of the profile flow: the client_id kept in localStorage, the last
 * ClientState, the trace of every request, and the A1 conversation. It is a plain
 * external store (subscribe / getSnapshot) consumed with useSyncExternalStore.
 */
import type { AnswerValue, ClientState, KnowledgeLevel, Locale, Question } from "@/lib/contract/schemas";
import type { PositionInput, UploadFile } from "@/lib/contract/requests";
import { ClientState as ClientStateSchema } from "@/lib/contract/schemas";
import { callAgent, callAgentStream, toApiError, type ApiError, type StreamHandlers } from "./api";
import { agentEntryOf, agentSpoke, MAX_RUNS, movedOn, newRun, uid, withNewRun, type ConversationEntry, type TraceRun } from "./session-history";
import { clearSessionStorage, readClientId, readHistory, writeClientId, writeHistory } from "./session-storage";

export type { AnsweredItem, ConversationEntry, TraceRun } from "./session-history";

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
  /**
   * After a failure, reads the runtime's state back: the request may have written part of its work (A1 fails
   * after the answers are saved) or all of it (the result was lost on the way, or the page was behind).
   */
  resync?: boolean;
  /** Set on the retry of a failed request. */
  retrying?: boolean;
}

/** What a request sends: `retrying` is true when the investor retries it after a failure. */
type RequestCall = (handlers: StreamHandlers, retrying: boolean) => Promise<ClientState>;

/** A request in flight: what it calls, how it shows, and the trace run that records it. */
interface PendingRequest {
  action: string;
  call: RequestCall;
  options: RequestOptions;
  run: TraceRun;
  started: number;
}

/**
 * Where the client_id comes from (CONTRACTS.md 7.1): this browser's localStorage (sign-in off), the
 * signed-in account (the server accepts no other), or nowhere yet (sign-in on, no session).
 */
export type ClientBinding = { source: "browser" } | { source: "account"; clientId: string } | { source: "none" };

/** The client_id to resume. An account's id replaces the one of this browser; an anonymous profile is not migrated. */
function initialClientId(binding: ClientBinding): string | null {
  if (binding.source === "none") return null;
  if (binding.source === "browser") return readClientId();
  if (readClientId() !== binding.clientId) writeClientId(binding.clientId);
  return binding.clientId;
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
  private binding: ClientBinding = { source: "browser" };
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

  /** Read localStorage (or the account's client_id) once, then resume the stored session if any. */
  init = async (binding: ClientBinding = { source: "browser" }): Promise<void> => {
    if (this.initialized) return;
    this.initialized = true;
    this.binding = binding;
    const clientId = initialClientId(binding);
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
      // A new account has no base yet: that is expected, `session.start` creates it.
      this.set({ ...INITIAL, hydrated: true, notice: this.binding.source === "account" ? null : "not_found" });
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
      (handlers, retrying) => {
        // A retry leaves out the answers the runtime has already written: it would refuse them as not pending.
        const sent = retrying ? this.stillPending(answers) : answers;
        return callAgentStream(
          {
            action: "followup.reply",
            client_id: clientId,
            ...(sent.length ? { answers: sent.map(({ question_id, value }) => ({ question_id, value })) } : {}),
            ...(message ? { message } : {}),
            ...(input.stop ? { stop: true } : {}),
          },
          handlers,
          this.options(),
        );
      },
      { streamed: true, userEntry, agentEntry: true, resync: true },
    );
  };

  /** The answers whose question the runtime still waits for, as the last state read says. */
  private stillPending<T extends { question_id: string }>(answers: T[]): T[] {
    const pending = new Set(this.snapshot.state?.questions.map((question) => question.id));
    return answers.filter((answer) => pending.has(answer.question_id));
  }

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

  private async execute(action: string, call: RequestCall, options: RequestOptions): Promise<boolean> {
    if (this.snapshot.pending) return false;
    const request: PendingRequest = { action, call, options, run: newRun(action, options), started: performance.now() };
    this.beginRequest(request);
    try {
      const result = await call(this.streamHandlers(), Boolean(options.retrying));
      this.completeRequest(request, result);
      return true;
    } catch (error) {
      const apiError = toApiError(error);
      // Still `pending` while the state is read back, so nothing else is sent in between.
      const fresh = options.resync && apiError.code !== "aborted" ? await this.readBack() : null;
      this.failRequest(request, apiError, fresh);
      return false;
    }
  }

  /** The state the runtime holds now (`session.resume`, no trace run); null if it cannot be read either. */
  private async readBack(): Promise<ClientState | null> {
    const clientId = this.snapshot.clientId;
    if (!clientId) return null;
    try {
      return await callAgent({ action: "session.resume", client_id: clientId, locale: this.locale }, ClientStateSchema, this.options());
    } catch {
      return null;
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
    const conversation =
      options.agentEntry && agentSpoke(result)
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

  /** `fresh`: the state read back after the failure, if any (`resync`). */
  private failRequest({ action, call, options, run, started }: PendingRequest, apiError: ApiError, fresh: ClientState | null): void {
    const failed: TraceRun = {
      ...run,
      status: "error",
      steps: this.snapshot.liveRun?.steps ?? [],
      durationMs: performance.now() - started,
      error: { code: apiError.code, message: apiError.message },
    };
    // The runtime is past the questions on screen (the result was lost on the way, or another tab answered):
    // its state replaces the error, and A1's last message joins the conversation. Nothing is left to retry.
    const caughtUp = fresh !== null && movedOn(this.snapshot.state, fresh);
    this.retryLast = caughtUp ? null : () => this.execute(action, call, { ...options, retrying: true });
    // The optimistic user entry is dropped: the composer keeps the text for a retry.
    const conversation = options.userEntry
      ? this.snapshot.conversation.filter((entry) => entry.id !== options.userEntry?.id)
      : this.snapshot.conversation;
    this.set({
      pending: null,
      liveRun: null,
      streamText: "",
      error: caughtUp ? null : apiError,
      errorAction: caughtUp ? null : action,
      runs: withNewRun(this.snapshot.runs, failed),
      conversation: caughtUp && agentSpoke(fresh) ? [...conversation, agentEntryOf(fresh)] : conversation,
      // Answered questions leave the screen, so neither a retry nor the next answer is refused as not pending.
      ...(fresh ? { state: fresh, revision: this.snapshot.revision + 1 } : {}),
    });
    this.persist();
  }
}
