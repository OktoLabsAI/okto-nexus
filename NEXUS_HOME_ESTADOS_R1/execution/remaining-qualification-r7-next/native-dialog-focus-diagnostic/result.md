# Browser-only diagnostic result

The single authorized static-dialog run completed 69 predicates, with no failures. It did not start Nexus, publish a question, use an account or invoke a provider.

Initial native dialog focus was the Expand modal button. All eleven synthetic controls were observed, counting that initial focus. At Tab-10, the document reported `hasFocus=false`, DOM/Playwright focus counts 0 and activeElement BODY; the dialog remained `:modal`. Tab-11 returned to Expand modal. The reverse traversal similarly reported outside-document focus at Shift+Tab-4, then returned to the event list at Shift+Tab-5. No focused external page control was observed while the modal was open. Escape closed the dialog and returned focus to its opener.

This establishes the behavior of this isolated native-dialog probe and demonstrates why a zero page-focus count alone is insufficient to diagnose a containment defect. It does not identify a particular browser chrome widget or establish the cause of the earlier Nexus I01 failure. That original cut remains partial and immutable.

Browser/probe exit0, cleanup errors/signals/forced containment absent, all observed own births/profile processes/listener65206 absent. Before/after pins matched, including 1,031 package payload, 1,829 source and 192 CLI files. The curated run manifest has no mismatches.

Evidence: `runs/hst-native-zoom-r9-dialog-focus-1/qualification.json`; manifest SHA256 `8948da83068cd432e43299ea22a47975ddf9f7e4f24ed59dc1b891da171879e3`.

The smallest future Nexus counterpart should record and count initial modal focus, inventory all actual visible/enabled controls, and distinguish a genuinely focused outside page control from an outside-document boundary. Any outside-document state should be recorded with the exact focus fields and followed with bounded benign Tab/Shift+Tab only; no manual trap or product change follows from this diagnostic. A new root review/gate is required before another application runtime.
