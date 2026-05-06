import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { cn } from "@/lib/utils";

type MarkdownMessageProps = {
  content: string;
};

export function MarkdownMessage({ content }: MarkdownMessageProps) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        a: ({ className, ...props }) => (
          <a
            className={cn("font-medium text-blue-700 underline underline-offset-2", className)}
            target="_blank"
            rel="noreferrer"
            {...props}
          />
        ),
        code: ({ className, children, ...props }) => (
          <code
            className={cn(
              "rounded bg-zinc-100 px-1.5 py-0.5 font-mono text-[0.9em] text-zinc-900",
              className,
            )}
            {...props}
          >
            {children}
          </code>
        ),
        pre: ({ className, ...props }) => (
          <pre
            className={cn(
              "my-3 overflow-x-auto rounded-md border border-zinc-200 bg-zinc-950 p-3 text-sm text-zinc-50",
              className,
            )}
            {...props}
          />
        ),
        table: ({ className, ...props }) => (
          <div className="my-3 overflow-x-auto">
            <table className={cn("w-full border-collapse text-left text-sm", className)} {...props} />
          </div>
        ),
        th: ({ className, ...props }) => (
          <th
            className={cn("border border-zinc-200 bg-zinc-50 px-2 py-1 font-semibold", className)}
            {...props}
          />
        ),
        td: ({ className, ...props }) => (
          <td className={cn("border border-zinc-200 px-2 py-1 align-top", className)} {...props} />
        ),
      }}
    >
      {content}
    </ReactMarkdown>
  );
}
