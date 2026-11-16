import type { ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { cn } from "./cn";

/** Renders a link itself, or returns `undefined` to keep the default rendering. */
export type LinkRenderer = (href: string | undefined, label: ReactNode) => ReactNode | undefined;

/** Agent messages and OKF bodies. Raw HTML is never rendered. */
export function Markdown({ children, className, renderLink }: { children: string; className?: string; renderLink?: LinkRenderer }) {
  return (
    <div className={cn("prose-af text-[0.95rem]", className)}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ href, children: label }) => {
            const custom = renderLink?.(href, label);
            if (custom !== undefined) return custom;
            const external = typeof href === "string" && /^https?:\/\//.test(href);
            return (
              <a href={href} {...(external ? { target: "_blank", rel: "noreferrer noopener" } : {})}>
                {label}
              </a>
            );
          },
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
