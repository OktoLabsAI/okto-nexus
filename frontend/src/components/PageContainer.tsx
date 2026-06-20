// Shared page wrapper: ONE deliberate decision for every screen's width +
// scroll, replacing the five ad-hoc max-w caps the views grew independently.
//   width="wide"     -> max-w-screen-2xl (data/grid screens; fills, 4K-safe)
//   width="readable" -> max-w-3xl        (single-column forms)
//   width="bleed"    -> no cap           (canvases: Graph, Handoffs, the
//                                          master-detail Messages/Events)
// Padding is one responsive rhythm; the bleed branch hands the full pane to a
// view that manages its own internal panes/scroll.

import { type ReactNode } from "react";

type Width = "wide" | "readable" | "bleed";
type Scroll = "y" | "x" | "none";

const CAP: Record<Exclude<Width, "bleed">, string> = {
  wide: "max-w-screen-2xl",
  readable: "max-w-3xl",
};

const OVERFLOW: Record<Scroll, string> = {
  y: "overflow-y-auto",
  x: "overflow-x-auto overflow-y-hidden",
  none: "overflow-hidden",
};

export function PageContainer({
  children,
  width = "wide",
  scroll = "y",
  className = "",
  testId,
}: {
  children: ReactNode;
  width?: Width;
  scroll?: Scroll;
  className?: string;
  testId?: string;
}) {
  if (width === "bleed") {
    return (
      <div
        className={`h-full ${OVERFLOW[scroll]} ${className}`}
        data-testid={testId}
      >
        {children}
      </div>
    );
  }
  return (
    <div className={`h-full ${OVERFLOW[scroll]} px-4 sm:px-6 lg:px-8 py-6`}>
      <div className={`${CAP[width]} mx-auto ${className}`} data-testid={testId}>
        {children}
      </div>
    </div>
  );
}
