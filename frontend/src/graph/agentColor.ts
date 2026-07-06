// Pure color helpers for the agent identity color (spec 2d6920f4).
//
// An agent's card header is tinted by its color: the operator-chosen color
// verbatim when set, else an "auto-by-identity" color derived deterministically
// from the agent_id (the same id always yields the same color; different ids
// generally differ). The name text color is chosen for contrast against the
// header. All functions are pure and total — a malformed input never throws,
// it falls back to the auto color — so the card always renders.

// FNV-1a → deterministic uint32 per id (identical to the graph layout seed
// hash, so identity is stable across reloads).
export function hashOf(id: string): number {
  let hash = 2166136261;
  for (let i = 0; i < id.length; i++) {
    hash = Math.imul(hash ^ id.charCodeAt(i), 16777619);
  }
  return hash >>> 0;
}

// Accepts #RGB or #RRGGBB (the same shape the REST layer validates).
const HEX_RE = /^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/;

export function isHexColor(value: unknown): value is string {
  return typeof value === "string" && HEX_RE.test(value.trim());
}

function hexToRgb(hex: string): { r: number; g: number; b: number } {
  let h = hex.trim().replace(/^#/, "");
  if (h.length === 3) {
    h = h
      .split("")
      .map((c) => c + c)
      .join("");
  }
  const int = parseInt(h, 16);
  return { r: (int >> 16) & 255, g: (int >> 8) & 255, b: int & 255 };
}

function rgbToHex(r: number, g: number, b: number): string {
  const to2 = (v: number) => {
    const n = Math.max(0, Math.min(255, Math.round(v)));
    return n.toString(16).padStart(2, "0");
  };
  return `#${to2(r)}${to2(g)}${to2(b)}`;
}

// HSL (h in [0,360), s/l in [0,1]) → hex. Fixed s/l keep every auto color
// legible under the header gradient; only the hue varies per id.
function hslToHex(h: number, s: number, l: number): string {
  const c = (1 - Math.abs(2 * l - 1)) * s;
  const hp = (((h % 360) + 360) % 360) / 60;
  const x = c * (1 - Math.abs((hp % 2) - 1));
  let r = 0;
  let g = 0;
  let b = 0;
  if (hp < 1) [r, g, b] = [c, x, 0];
  else if (hp < 2) [r, g, b] = [x, c, 0];
  else if (hp < 3) [r, g, b] = [0, c, x];
  else if (hp < 4) [r, g, b] = [0, x, c];
  else if (hp < 5) [r, g, b] = [x, 0, c];
  else [r, g, b] = [c, 0, x];
  const m = l - c / 2;
  return rgbToHex((r + m) * 255, (g + m) * 255, (b + m) * 255);
}

// The stable auto-by-identity color: hue from the id hash, fixed s/l.
export function autoColor(id: string): string {
  return hslToHex(hashOf(id) % 360, 0.58, 0.55);
}

// The card header base color for an agent: the stored color verbatim when it is
// a valid hex, else the auto-by-identity color. Never throws.
export function agentColor(id: string, stored?: string | null): string {
  return isHexColor(stored) ? stored.trim() : autoColor(id);
}

// Lighten (amount>0, toward white) or darken (amount<0, toward black) by ratio.
function shade(hex: string, amount: number): string {
  const { r, g, b } = hexToRgb(hex);
  const target = amount < 0 ? 0 : 255;
  const p = Math.abs(amount);
  return rgbToHex(
    r + (target - r) * p,
    g + (target - g) * p,
    b + (target - b) * p,
  );
}

// A SUBTLE ("leve") header gradient: the base color eased a touch lighter at
// the top-left to a touch darker at the bottom-right. Small deltas keep it a
// soft sheen, not a loud two-tone band.
export function gradientFor(hex: string): string {
  return `linear-gradient(135deg, ${shade(hex, 0.12)}, ${shade(hex, -0.14)})`;
}

// WCAG relative luminance of a hex color, in [0,1].
export function relativeLuminance(hex: string): number {
  const { r, g, b } = hexToRgb(hex);
  const lin = (v: number) => {
    const s = v / 255;
    return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
  };
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
}

// Contrast-aware header text: near-black ink over a light header, near-white
// over a dark one. The 0.179 threshold is the WCAG crossover where black vs
// white flips the higher contrast ratio against the header color.
export function textColorFor(hex: string): string {
  return relativeLuminance(hex) > 0.179 ? "#0b1220" : "#f8fafc";
}
