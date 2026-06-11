// Compact markdown renderer for chat bubbles (react-markdown + GFM).
// Safe by construction: react-markdown builds a React tree, never raw HTML
// (agent-authored bodies are untrusted input). Components are styled inline
// because Tailwind's preflight strips element defaults inside the app.

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export function Markdown({ text }: { text: string }) {
  return (
    <div className="chat-md break-words">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          p: ({ children }) => <p className="my-1 first:mt-0 last:mb-0">{children}</p>,
          a: ({ href, children }) => (
            <a
              href={href}
              target="_blank"
              rel="noreferrer"
              className="underline text-accent-600 dark:text-accent-400"
            >
              {children}
            </a>
          ),
          ul: ({ children }) => (
            <ul className="list-disc pl-4 my-1 space-y-0.5">{children}</ul>
          ),
          ol: ({ children }) => (
            <ol className="list-decimal pl-4 my-1 space-y-0.5">{children}</ol>
          ),
          li: ({ children }) => <li>{children}</li>,
          h1: ({ children }) => (
            <h1 className="font-semibold text-[12px] mt-1.5 mb-0.5">{children}</h1>
          ),
          h2: ({ children }) => (
            <h2 className="font-semibold text-[12px] mt-1.5 mb-0.5">{children}</h2>
          ),
          h3: ({ children }) => (
            <h3 className="font-semibold mt-1 mb-0.5">{children}</h3>
          ),
          h4: ({ children }) => (
            <h4 className="font-semibold mt-1 mb-0.5">{children}</h4>
          ),
          code: ({ className, children }) =>
            className ? (
              // fenced block (language-*): rendered by <pre> below
              <code className={className}>{children}</code>
            ) : (
              <code className="px-1 py-px rounded bg-black/10 dark:bg-white/10 font-mono text-[10px]">
                {children}
              </code>
            ),
          pre: ({ children }) => (
            <pre className="my-1 p-2 rounded-lg bg-black/10 dark:bg-black/40 overflow-x-auto font-mono text-[10px] leading-snug">
              {children}
            </pre>
          ),
          blockquote: ({ children }) => (
            <blockquote className="border-l-2 border-surface-300 dark:border-surface-600 pl-2 my-1 opacity-80">
              {children}
            </blockquote>
          ),
          hr: () => <hr className="my-1.5 border-surface-300/60 dark:border-surface-600/60" />,
          table: ({ children }) => (
            <div className="overflow-x-auto my-1">
              <table className="text-[10px] border-collapse">{children}</table>
            </div>
          ),
          th: ({ children }) => (
            <th className="border border-surface-300 dark:border-surface-600 px-1.5 py-0.5 font-semibold text-left">
              {children}
            </th>
          ),
          td: ({ children }) => (
            <td className="border border-surface-300 dark:border-surface-600 px-1.5 py-0.5">
              {children}
            </td>
          ),
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
}
