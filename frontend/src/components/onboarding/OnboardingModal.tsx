// OnboardingModal - first-run, 4-slide intro to Okto Nexus (mirrors the Okto
// Pulse onboarding pattern: slide state machine, step indicator, dot footer,
// keyboard nav + focus-trap, versioned-localStorage completion). Teaches the
// real flow: register an agent -> connect it over MCP -> observe the mesh.
//
// Visual identity is the Nexus mark's diagonal blue->violet ramp on key
// concepts (bg-clip-text), General Sans display + mono labels, light/dark
// parity - consistent with About/Help and the dashboard shell.

import { useCallback, useEffect, useReducer, useRef } from "react";
import { Moon, Sun, X } from "lucide-react";
import { useTheme } from "../../hooks/useTheme";
import { markCompleted } from "./onboardingStorage";

const TOTAL_SLIDES = 4;

// The brand ramp as a text-clip accent (same stops as logos/nexus-icon.svg).
const ACCENT =
  "bg-gradient-to-r from-[#2438f0] via-[#5b32f4] to-[#9b2cf0] " +
  "bg-clip-text text-transparent";
const ACCENT_BG = "linear-gradient(90deg, #2438f0, #5b32f4, #9b2cf0)";

type SlideState = 1 | 2 | 3 | 4;
type SlideEvent = { type: "NEXT" | "BACK" };

function reducer(state: SlideState, event: SlideEvent): SlideState {
  if (event.type === "NEXT") return Math.min(TOTAL_SLIDES, state + 1) as SlideState;
  return Math.max(1, state - 1) as SlideState;
}

const TITLE_ID = "onboarding-slide-title";

function mcpUrlPlaceholder(): string {
  const host = typeof location !== "undefined" ? location.hostname : "127.0.0.1";
  const port =
    typeof location !== "undefined" && location.port ? location.port : "8202";
  return `http://${host}:${port}/mcp?api_key=nxs_…`;
}

export function OnboardingModal({ onClose }: { onClose: () => void }) {
  const [slide, dispatch] = useReducer(reducer, 1 as SlideState);
  const { theme, toggle: toggleTheme } = useTheme();
  const containerRef = useRef<HTMLDivElement>(null);
  const ctaRef = useRef<HTMLButtonElement>(null);
  const liveRef = useRef<HTMLDivElement>(null);

  const close = useCallback(() => {
    markCompleted();
    onClose();
  }, [onClose]);

  // Keyboard: Esc closes; Left/Right navigate (outside inputs); Tab is trapped.
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        close();
        return;
      }
      const t = e.target as HTMLElement | null;
      const editable =
        t?.tagName === "INPUT" || t?.tagName === "TEXTAREA" || t?.isContentEditable;
      if (e.key === "ArrowRight" && !editable) {
        e.preventDefault();
        dispatch({ type: "NEXT" });
      } else if (e.key === "ArrowLeft" && !editable) {
        e.preventDefault();
        dispatch({ type: "BACK" });
      } else if (e.key === "Tab" && containerRef.current) {
        const f = containerRef.current.querySelectorAll<HTMLElement>(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
        );
        if (f.length === 0) return;
        const first = f[0];
        const last = f[f.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [close]);

  // Focus the CTA and announce each slide for screen readers.
  useEffect(() => {
    ctaRef.current?.focus();
    if (liveRef.current) {
      liveRef.current.textContent = `Slide ${slide} of ${TOTAL_SLIDES}`;
    }
  }, [slide]);

  const isLast = slide === TOTAL_SLIDES;
  const onBackdrop = (e: React.MouseEvent<HTMLDivElement>) => {
    if (e.target === e.currentTarget) close();
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby={TITLE_ID}
      data-testid="onboarding-modal"
      data-slide={slide}
      className="fixed inset-0 z-[1100] flex items-center justify-center bg-black/50 backdrop-blur-sm p-4"
      onMouseDown={onBackdrop}
    >
      <div
        ref={containerRef}
        className="w-full max-w-xl bg-white dark:bg-[#0b1929] border border-surface-200/60 dark:border-[#142840] rounded-2xl shadow-2xl overflow-hidden"
      >
        {/* Header */}
        <header className="flex items-center justify-between px-6 py-3.5 border-b border-surface-200/60 dark:border-[#142840]">
          <span className="font-mono text-[11px] uppercase tracking-[0.15em] text-surface-400 dark:text-surface-500">
            0{slide} / 0{TOTAL_SLIDES} · Onboarding
          </span>
          <div className="flex items-center gap-2.5">
            <button
              type="button"
              onClick={toggleTheme}
              aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
              className="w-8 h-8 rounded-lg border border-surface-200 dark:border-surface-700 text-surface-500 dark:text-surface-400 hover:bg-surface-100 dark:hover:bg-surface-800 transition-colors flex items-center justify-center"
            >
              {theme === "dark" ? <Sun size={14} /> : <Moon size={14} />}
            </button>
            <button
              type="button"
              onClick={close}
              aria-label="Close onboarding"
              data-testid="onboarding-close"
              className="w-8 h-8 rounded-lg border border-surface-200 dark:border-surface-700 text-surface-500 dark:text-surface-400 hover:bg-surface-100 dark:hover:bg-surface-800 transition-colors flex items-center justify-center"
            >
              <X size={14} />
            </button>
          </div>
        </header>

        {/* Body */}
        <main className="px-10 py-9 min-h-[360px] text-surface-900 dark:text-white">
          {slide === 1 && <WelcomeSlide />}
          {slide === 2 && <RegisterSlide />}
          {slide === 3 && <ConnectSlide />}
          {slide === 4 && <ObserveSlide />}
        </main>

        {/* Footer */}
        <footer className="flex items-center justify-between px-6 py-3.5 border-t border-surface-200/60 dark:border-[#142840]">
          <div
            role="tablist"
            aria-label="Slide indicator"
            className="flex items-center gap-1.5"
          >
            {Array.from({ length: TOTAL_SLIDES }, (_, i) => {
              const active = i + 1 === slide;
              return (
                <span
                  key={i}
                  role="tab"
                  aria-selected={active}
                  aria-label={`Slide ${i + 1}${active ? " (current)" : ""}`}
                  className={
                    active
                      ? "h-1 w-8 rounded-full"
                      : "h-1 w-2 rounded-full bg-surface-300 dark:bg-surface-700"
                  }
                  style={active ? { background: ACCENT_BG } : undefined}
                />
              );
            })}
          </div>
          <div className="flex items-center gap-2.5">
            {slide > 1 && (
              <button
                type="button"
                onClick={() => dispatch({ type: "BACK" })}
                className="text-sm text-surface-500 dark:text-surface-400 px-3 py-1.5 rounded-lg border border-surface-200 dark:border-surface-700 hover:bg-surface-50 dark:hover:bg-surface-800 transition-colors"
              >
                ← Back
              </button>
            )}
            <button
              ref={ctaRef}
              type="button"
              onClick={() => (isLast ? close() : dispatch({ type: "NEXT" }))}
              data-testid="onboarding-cta"
              className="text-[13px] font-semibold text-white px-4 py-2 rounded-lg border-0 cursor-pointer tracking-wide"
              style={{ background: ACCENT_BG }}
            >
              {isLast ? "Get started" : "Next →"}
            </button>
          </div>
        </footer>

        <div ref={liveRef} role="status" aria-live="polite" className="sr-only" />
      </div>
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Slides
// --------------------------------------------------------------------------- //
function SlideLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-surface-400 dark:text-surface-500 mb-3.5">
      {children}
    </div>
  );
}

function WelcomeSlide() {
  return (
    <div className="text-center">
      <img
        src="/logos/nexus-icon.svg"
        alt="Okto Nexus"
        className="w-16 h-16 mx-auto mb-4 select-none"
        draggable={false}
      />
      <div className="font-mono text-[10px] uppercase tracking-[0.2em] text-surface-400 dark:text-surface-500 mb-3">
        Okto Labs · Coordination bus
      </div>
      <h1
        id={TITLE_ID}
        className="font-display text-3xl font-semibold tracking-tight mb-4 leading-tight"
      >
        Welcome to <span className={ACCENT}>Okto Nexus</span>
      </h1>
      <p className="text-[15px] leading-relaxed text-surface-500 dark:text-surface-400 max-w-md mx-auto mb-6">
        The local bus where your agents <span className={ACCENT}>discover each
        other</span>, exchange messages, hand off work — and you watch it all
        happen live.
      </p>
      <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full border border-surface-200 dark:border-surface-700 text-xs text-surface-500 dark:text-surface-400 font-mono">
        <span
          className="w-1.5 h-1.5 rounded-full inline-block"
          style={{ background: ACCENT_BG }}
        />
        Register → Connect → Coordinate → Observe
      </div>
    </div>
  );
}

function RegisterSlide() {
  const steps = [
    ["Open the Agents tab", "Left sidebar → Agents."],
    ["Create an agent", "Give it an id, role and capabilities."],
    ["Copy its API key", "nxs_… — shown once. The key IS the identity."],
  ];
  return (
    <div>
      <SlideLabel>01 · Agent identity</SlideLabel>
      <h2 id={TITLE_ID} className="font-display text-2xl font-semibold tracking-tight mb-4">
        Every participant is an <span className={ACCENT}>agent</span>
      </h2>
      <p className="text-[13.5px] leading-snug text-surface-500 dark:text-surface-400 mb-5">
        Agents are global identities on the bus — humans and AI tools join the
        same way. Each one carries an API key that authenticates it.
      </p>
      <ol className="space-y-2.5">
        {steps.map(([title, desc], i) => (
          <li key={title} className="flex items-start gap-3">
            <span
              className="shrink-0 w-6 h-6 rounded-full text-white text-[11px] font-semibold grid place-items-center mt-0.5"
              style={{ background: ACCENT_BG }}
            >
              {i + 1}
            </span>
            <div>
              <div className="text-sm font-medium text-surface-800 dark:text-surface-200">
                {title}
              </div>
              <div className="text-[12.5px] text-surface-500 dark:text-surface-400">
                {desc}
              </div>
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}

const CLIENTS = ["Claude Code", "Codex", "Cursor", "Windsurf", "VS Code"] as const;

function ConnectSlide() {
  const url = mcpUrlPlaceholder();
  return (
    <div>
      <SlideLabel>02 · Connect</SlideLabel>
      <h2 id={TITLE_ID} className="font-display text-2xl font-semibold tracking-tight mb-4">
        Wire your <span className={ACCENT}>coding agent</span>
      </h2>
      <p className="text-[13.5px] leading-snug text-surface-500 dark:text-surface-400 mb-4">
        From the Agents tab, copy the agent's{" "}
        <span className="font-mono text-accent-600 dark:text-accent-400">MCP config</span>{" "}
        URL and paste it into your assistant. The key in the URL is the agent's
        identity on every call.
      </p>
      <div className="font-mono flex items-center gap-3 px-3.5 py-3 mb-4 rounded-xl border border-surface-200 dark:border-surface-700 bg-surface-50 dark:bg-surface-900">
        <code className="text-[12px] text-accent-600 dark:text-accent-400 truncate min-w-0">
          {url}
        </code>
      </div>
      <div className="font-mono text-[11px] uppercase tracking-[0.1em] text-surface-400 dark:text-surface-500 mb-2.5">
        Works with any MCP client
      </div>
      <div className="grid grid-cols-5 gap-2">
        {CLIENTS.map((c) => (
          <div
            key={c}
            className="px-2 py-2.5 border border-surface-200 dark:border-surface-700 rounded-lg text-center text-[11px] text-surface-500 dark:text-surface-400"
          >
            {c}
          </div>
        ))}
      </div>
    </div>
  );
}

function ObserveSlide() {
  const legend: [string, string, string][] = [
    ["#0ea5e9", "Agents are nodes", "colour shows presence — present, stale, offline."],
    ["#22d3ee", "Edges are messages", "cyan/dashed = in-flight; grey = completed flow."],
    ["#ec4899", "Squares are handoffs", "work waiting in the pool for a free agent to claim."],
  ];
  return (
    <div>
      <SlideLabel>03 · Observe</SlideLabel>
      <h2 id={TITLE_ID} className="font-display text-2xl font-semibold tracking-tight mb-4">
        Watch the <span className={ACCENT}>mesh</span> live
      </h2>
      <p className="text-[13.5px] leading-snug text-surface-500 dark:text-surface-400 mb-5">
        The Graph is your live view of the swarm. Messages addressed to an agent
        land in its inbox; click any element to inspect it.
      </p>
      <ul className="space-y-3">
        {legend.map(([color, title, desc]) => (
          <li key={title} className="flex items-start gap-3">
            <span
              className="shrink-0 w-3 h-3 rounded-full mt-1"
              style={{ background: color }}
            />
            <div>
              <div className="text-sm font-medium text-surface-800 dark:text-surface-200">
                {title}
              </div>
              <div className="text-[12.5px] text-surface-500 dark:text-surface-400">
                {desc}
              </div>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
