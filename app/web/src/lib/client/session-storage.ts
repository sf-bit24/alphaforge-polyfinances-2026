/**
 * Where the client session is kept between visits: the client_id, then the trace runs and
 * the conversation of that client, in localStorage. Storage may be full or disabled: every
 * access tolerates it, and the session still works for this tab.
 */
import type { ConversationEntry, TraceRun } from "./session-history";

const KEY_CLIENT = "alphaforge.client_id";
const keyRuns = (id: string) => `alphaforge.runs.${id}`;
const keyConversation = (id: string) => `alphaforge.conversation.${id}`;

function readJson<T>(key: string, fallback: T): T {
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

function writeJson(key: string, value: unknown): void {
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Storage full or disabled: the session still works for this tab.
  }
}

export function readClientId(): string | null {
  try {
    return window.localStorage.getItem(KEY_CLIENT);
  } catch {
    return null;
  }
}

export function readHistory(clientId: string): { runs: TraceRun[]; conversation: ConversationEntry[] } {
  return {
    runs: readJson<TraceRun[]>(keyRuns(clientId), []),
    conversation: readJson<ConversationEntry[]>(keyConversation(clientId), []),
  };
}

export function writeClientId(clientId: string): void {
  try {
    window.localStorage.setItem(KEY_CLIENT, clientId);
  } catch {
    // ignore
  }
}

export function writeHistory(clientId: string, runs: TraceRun[], conversation: ConversationEntry[]): void {
  writeJson(keyRuns(clientId), runs);
  writeJson(keyConversation(clientId), conversation);
}

export function clearSessionStorage(clientId: string): void {
  try {
    window.localStorage.removeItem(KEY_CLIENT);
    window.localStorage.removeItem(keyRuns(clientId));
    window.localStorage.removeItem(keyConversation(clientId));
  } catch {
    // ignore
  }
}
