# I01 first keyboard cut — partial, no PASS claim

The single authorized execution stopped on its first failing predicate and exited 1. Native zoom calibration passed 14 checks and Native100/desktop bootstrap passed three. The app keyboard phase recorded 52 positive predicates and one failed predicate, `active-focused-element-present-10`.

The real Home traversal visited all 23 inventoried visible/enabled sequential controls with no missing item, using Tab only. Their actual AX names, focus-visible state and painted outline/shadow passed. Enter on the known B1 Follow activity opened the exact retained session: real GET 200 and all twelve expected scope fields matched; the output marker was present. The dialog matched the UA `:modal` predicate.

The dialog inventory counted eleven controls. Ten subsequent Tab positions were observed inside it with named AX controls and painted focus, ending at the Live runtime events list. The next Tab did not satisfy the assertion that exactly one `:focus` element existed in the page. The failing predicate's `actual: true` is a literal instrumentation limitation: the real count, `document.hasFocus()` and active-element identity were not serialized in that branch. Initial modal focus was also not recorded as an inventory visit. Therefore the evidence does **not** establish whether focus went to browser chrome, an unrecorded element, or escaped into application content. It does not prove a product containment defect. The source uses native `showModal()`; this source fact is not a substitute for the missing runtime observation.

Needs-you/Results activation, complete modal coverage, Escape/return and the end-of-case zero-write assertions were not reached. Those clauses remain unqualified. No runtime was repeated or modified; no productive control was activated by the script.

The original diagnostic evidence is in `runs/hst-native-zoom-r9-keyboard-1/qualification.json` and its immutable manifest. Before/after match for 1,031 payload, 1,829 source and 192 CLI files plus the other pinned inputs. Browser/probe/fixture exited normally; no cleanup error, signal or forced containment was recorded. All observed own process births, the profile and listeners 63111/56965 were absent. B1 canonical close was confirmed; A1/A2 remain UNKNOWN. Physical absence does not settle those receipts.

No I01 task PASS, AT speech, I04/theme, human acceptance or performance claim is made. A future counterpart requires a new root review/gate and should record initial focus and exact failure observations before diagnosing product versus oracle.
