# Home overview clarification

The delivered Home summarizes agents/activity, harness conversations, recent communications and attention, with direct navigation. Herdr reports remain explicitly separate from managed sessions. This is the user clarification delivered in commit d3713c43; the fixed R3 plan is unchanged.

41 distinct tests passed (6 Home +35 regressions), and the final static build passed. Root reviewed the actual App using synthetic API fixtures at desktop1440×1000 and mobile390×844. Initial mobile119px content failed; final343px content has no horizontal overflow. Escape closes the mobile overlay and preserves desktop preference. Final screenshots are retained; they do not prove a live service or M1.
