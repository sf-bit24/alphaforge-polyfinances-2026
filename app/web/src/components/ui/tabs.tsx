"use client";

import { useRef, type KeyboardEvent, type ReactNode } from "react";
import { cn } from "./cn";

export interface TabItem<T extends string> {
  id: T;
  label: string;
  icon?: ReactNode;
}

interface TabListProps<T extends string> {
  tabs: ReadonlyArray<TabItem<T>>;
  value: T;
  onChange: (tab: T) => void;
  /** Prefix of the tab and panel ids, shared with `tabPanelProps`. */
  idPrefix: string;
  label: string;
  className?: string;
}

const KEY_STEP: Record<string, (index: number, count: number) => number> = {
  ArrowRight: (index, count) => (index + 1) % count,
  ArrowLeft: (index, count) => (index - 1 + count) % count,
  Home: () => 0,
  End: (_index, count) => count - 1,
};

export const tabId = (idPrefix: string, id: string) => `${idPrefix}-tab-${id}`;
export const panelId = (idPrefix: string, id: string) => `${idPrefix}-panel-${id}`;

/** ARIA tabs: arrow keys, Home and End move between tabs and select them (automatic activation). */
export function TabList<T extends string>({ tabs, value, onChange, idPrefix, label, className }: TabListProps<T>) {
  const buttons = useRef(new Map<string, HTMLButtonElement>());
  const onKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    const step = KEY_STEP[event.key];
    const next = step ? tabs[step(index, tabs.length)] : undefined;
    if (!next) return;
    event.preventDefault();
    onChange(next.id);
    buttons.current.get(next.id)?.focus();
  };
  return (
    <div role="tablist" aria-label={label} className={cn("flex gap-1 overflow-x-auto border-b border-ink-200", className)}>
      {tabs.map((tab, index) => {
        const selected = tab.id === value;
        return (
          <button
            key={tab.id}
            ref={(element) => {
              if (element) buttons.current.set(tab.id, element);
              else buttons.current.delete(tab.id);
            }}
            type="button"
            role="tab"
            id={tabId(idPrefix, tab.id)}
            aria-selected={selected}
            aria-controls={panelId(idPrefix, tab.id)}
            tabIndex={selected ? 0 : -1}
            onClick={() => onChange(tab.id)}
            onKeyDown={(event) => onKeyDown(event, index)}
            className={cn(
              "-mb-px inline-flex items-center gap-2 border-b-2 px-3 py-2.5 text-sm font-medium whitespace-nowrap transition-colors",
              "focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-focus",
              selected ? "border-brand-600 text-ink-950" : "border-transparent text-ink-600 hover:border-ink-300 hover:text-ink-900",
            )}
          >
            {tab.icon}
            {tab.label}
          </button>
        );
      })}
    </div>
  );
}

/** Props of the panel of tab `id`; a hidden panel stays mounted, so its state and polling survive. */
export function tabPanelProps(idPrefix: string, id: string, selected: boolean) {
  return { role: "tabpanel", id: panelId(idPrefix, id), "aria-labelledby": tabId(idPrefix, id), hidden: !selected } as const;
}
