// Nexus loading animation — the brand mark, alive.
//
// The Okto Nexus icon IS a coordination bus: a central hub agent wired to
// satellite agents. So the loader doesn't spin — it TRANSMITS. The hub
// breathes and emits halo ripples; a light "signal" travels each connector
// out to a satellite, which lights up in turn (a rotating transmission
// rhythm). Pure stroke geometry on the brand's diagonal blue->violet ramp,
// matching the static icon (logos/nexus-icon.svg). Theme-agnostic (the
// gradient reads on light and dark); honours prefers-reduced-motion.
import { useId } from "react";

export function NexusLoader({
  size = 64,
  label,
  className = "",
}: {
  /** Edge length of the square mark, in px. */
  size?: number;
  /** Optional caption rendered under the mark (e.g. "Loading conversation…"). */
  label?: string;
  className?: string;
}) {
  // One gradient id per instance: several loaders can coexist on a page
  // without their <defs> colliding.
  const gid = useId().replace(/[:]/g, "");
  const grad = `nxl-grad-${gid}`;

  return (
    <div
      className={`nxl-root inline-flex flex-col items-center justify-center gap-3 ${className}`}
      role="status"
      aria-live="polite"
      aria-busy="true"
    >
      <svg
        width={size}
        height={size}
        viewBox="0 0 32 32"
        fill="none"
        aria-label={label ?? "Carregando"}
      >
        <defs>
          {/* userSpaceOnUse: one ramp spans the whole mark, so every circle
              and connector samples the same continuous blue->violet ramp. */}
          <linearGradient
            id={grad}
            gradientUnits="userSpaceOnUse"
            x1="2"
            y1="30"
            x2="30"
            y2="2"
          >
            <stop offset="0%" stopColor="#2438f0" />
            <stop offset="55%" stopColor="#5b32f4" />
            <stop offset="100%" stopColor="#9b2cf0" />
          </linearGradient>
        </defs>

        {/* Halo ripples emanating from the hub — the bus broadcasting. */}
        <g stroke={`url(#${grad})`} fill="none" strokeWidth="1">
          <circle className="nxl-ring nxl-ring-1" cx="14.5" cy="14.5" r="5.8" />
          <circle className="nxl-ring nxl-ring-2" cx="14.5" cy="14.5" r="5.8" />
        </g>

        {/* Connector rails (faint baseline the signal rides over). */}
        <g
          stroke={`url(#${grad})`}
          strokeWidth="1.2"
          strokeLinecap="round"
          fill="none"
          opacity="0.16"
        >
          <line x1="19.3" y1="10.8" x2="21.1" y2="9.4" />
          <line x1="18.9" y1="18.7" x2="21.7" y2="21.4" />
          <line x1="10.46" y1="19.07" x2="9.05" y2="20.68" />
        </g>

        {/* Travelling signals — a short dash sweeps hub -> satellite. The
            pathLength=100 normalisation lets every rail share one animation
            despite differing real lengths. */}
        <g stroke={`url(#${grad})`} strokeWidth="1.5" strokeLinecap="round" fill="none">
          <line className="nxl-spark nxl-spark-1" pathLength={100} x1="19.3" y1="10.8" x2="21.1" y2="9.4" />
          <line className="nxl-spark nxl-spark-2" pathLength={100} x1="18.9" y1="18.7" x2="21.7" y2="21.4" />
          <line className="nxl-spark nxl-spark-3" pathLength={100} x1="10.46" y1="19.07" x2="9.05" y2="20.68" />
        </g>

        {/* Hub agent — breathing. */}
        <circle
          className="nxl-hub"
          cx="14.5"
          cy="14.5"
          r="5.8"
          fill="none"
          stroke={`url(#${grad})`}
          strokeWidth="1.2"
        />

        {/* Satellite agents — light up as their signal arrives (staggered). */}
        <g fill="none" stroke={`url(#${grad})`} strokeWidth="1.2">
          <circle className="nxl-sat nxl-sat-1" cx="23.5" cy="7.5" r="2.8" />
          <circle className="nxl-sat nxl-sat-2" cx="24" cy="23.5" r="2.8" />
          <circle className="nxl-sat nxl-sat-3" cx="7" cy="23" r="2.8" />
        </g>
      </svg>

      {label && (
        <span className="nxl-label font-display text-xs font-medium tracking-wide text-surface-500 dark:text-surface-400">
          {label}
        </span>
      )}

      <style>{NXL_CSS}</style>
    </div>
  );
}

// Centered full-area loader for empty panels (graph canvas, chat panel,
// settings view) — drops straight into a flex/grid container.
export function NexusLoaderFill({
  label,
  size = 72,
}: {
  label?: string;
  size?: number;
}) {
  return (
    <div className="flex-1 min-h-0 grid place-items-center p-6">
      <NexusLoader size={size} label={label} />
    </div>
  );
}

const NXL_CSS = `
.nxl-hub {
  transform-box: fill-box;
  transform-origin: center;
  animation: nxlBreathe 2.4s ease-in-out infinite;
}
.nxl-ring {
  transform-box: fill-box;
  transform-origin: center;
  animation: nxlRipple 2.2s ease-out infinite;
}
.nxl-ring-2 { animation-delay: 1.1s; }

.nxl-spark {
  stroke-dasharray: 18 100;
  stroke-dashoffset: 18;
  animation: nxlFlow 2s cubic-bezier(0.45, 0, 0.55, 1) infinite;
}
.nxl-spark-2 { animation-delay: 0.22s; }
.nxl-spark-3 { animation-delay: 0.44s; }

.nxl-sat {
  transform-box: fill-box;
  transform-origin: center;
  opacity: 0.4;
  animation: nxlBlink 2s ease-in-out infinite;
}
.nxl-sat-2 { animation-delay: 0.22s; }
.nxl-sat-3 { animation-delay: 0.44s; }

.nxl-label { animation: nxlLabel 2s ease-in-out infinite; }

@keyframes nxlBreathe {
  0%, 100% { transform: scale(1);    opacity: 0.85; }
  50%      { transform: scale(1.06); opacity: 1; }
}
@keyframes nxlRipple {
  0%   { transform: scale(1);    opacity: 0.5; }
  70%  { opacity: 0; }
  100% { transform: scale(1.95); opacity: 0; }
}
@keyframes nxlFlow {
  0%   { stroke-dashoffset: 18;   opacity: 0; }
  14%  { opacity: 1; }
  58%  { opacity: 1; }
  72%  { stroke-dashoffset: -100; opacity: 0; }
  100% { stroke-dashoffset: -100; opacity: 0; }
}
@keyframes nxlBlink {
  0%, 48% { opacity: 0.4;  transform: scale(1); }
  66%     { opacity: 1;    transform: scale(1.3); }
  82%     { opacity: 0.55; transform: scale(1); }
  100%    { opacity: 0.4;  transform: scale(1); }
}
@keyframes nxlLabel {
  0%, 100% { opacity: 0.55; }
  50%      { opacity: 1; }
}

/* Reduced motion: hold a crisp, static, fully-formed mark — no sweep. */
@media (prefers-reduced-motion: reduce) {
  .nxl-spark { opacity: 0 !important; animation: none !important; }
  .nxl-ring  { display: none !important; }
  .nxl-hub, .nxl-sat, .nxl-label {
    animation: none !important;
    opacity: 1 !important;
    transform: none !important;
  }
}
`;
