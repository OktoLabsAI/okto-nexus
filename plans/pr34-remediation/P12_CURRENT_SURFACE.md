# Current optional MCP surface

Source: `5d1d17874c2d62f94b8e329fafbdc3880c4af4e5`, with production identical to
39c5e6c. Surface revision58 / identity25. This metadata-only measurement completed
with exit0 while full Windows/Linux suites continued; it is not their result.

| Source / configuration | Tools | Total characters | Cuttable characters |
|---|---:|---:|---:|
| Original PR34, OFF or ON | 51 | 45744 | 33689 |
| Current, OFF | 43 | 40264 | 28131 |
| Current, ON | 51 | 47644 | 32091 |

The current opt-in adds exactly the eight harness tools,7380 total characters and
3960 cuttable characters. Compared with original ON, total growth is1900 characters
and cuttable text falls1598 characters. No new tool per adapter or growth exemption
was introduced. Tokens in the instrument are characters/4 proxies, not tokenizer
measurements. Historical revision56 measurements remain in P12_API_REVIEW.md.

Command: `rtk proxy python -X utf8 plans/pr34-remediation/measure_surface.py d7d87d0c3ee2ea2ed7c63cdb8f9cafdbd5ee0397`.
The launcher set TEMP/TMP/TMPDIR to a fresh private directory on D; exact overrides,
script hash, source SHAs and raw numeric results are in
[evidence/p12-surface-58.json](evidence/p12-surface-58.json). The script creates
fresh homes and an isolated git archive, sanitizes child environments and queries
actual FastMCP schemas. No provider, personal database or operator token was used.

Backlog maintenance at this same snapshot links later scoped acceptance documents
to59 implementation tasks outside P00. The four P00 baseline tasks retain their
original baseline evidence. Historical notes are preserved; `current_review`
points to later evidence without promoting any task/phase status. T-API-01 remains
FAIL until receipt correction integration; native Pi/dedicated attach and the final
report gates remain explicitly unqualified.
