# Native-dialog observation counterpart — prepared only

Original I01 first cut remains partial, with its original failed oracle and incomplete failure observation. The standalone native-dialog diagnostic is separate evidence and does not retroactively establish the original cause.

This counterpart counts and validates the actual initial modal focus as part of the exact visible/enabled inventory. It serializes DOM/locator focus counts, document.hasFocus, active element/path/:focus, UA modal/open state, focus painting, and focusin/focusout/window focus/blur events at each observation. Actual focus or focusin into background page content while the modal is open is a failure.

An outside-document boundary is accepted only when hasFocus is false, DOM/locator focus counts are both zero, active element does not match :focus and the UA modal remains open. It is recorded without claiming a particular browser chrome widget. Bounded real Tab/Shift+Tab must return to the modal, with no focus(), trap or application state manipulation. Initial focus plus subsequent Tab observations must cover all inventoried controls.

The same exact retained session, original native request and result targets, request-control readiness, Escape and originating-card return assertions remain. No Copy/submit/decision/answer selection is activated. Native100 precedes app/question, original120s lease/question and150s peer stay unchanged, supervisor300/actions180/cleanup120. First failure stops. No product change or automatic rerun.

References: [W3C H102](https://www.w3.org/WAI/WCAG22/Techniques/html/H102) and [Chrome native dialogs](https://developer.chrome.com/docs/modern-web-guidance/guides/accessibility/accessibility#native-dialog), checked for the earlier isolated probe. Their platform guidance does not replace the new actual Nexus observations.

Proposed command after a new root gate:

`rtk proxy python -B -Xutf8 NEXUS_HOME_ESTADOS_R1/execution/remaining-qualification-r7-next/keyboard-app-r9-prepared/run_v3.py --gate NEXUS_HOME_ESTADOS_R1/execution/remaining-qualification-r7-next/keyboard-app-r9-prepared/ROOT-GATE-v3.json`
