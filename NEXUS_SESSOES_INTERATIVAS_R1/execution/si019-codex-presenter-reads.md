# SI-019 exact Codex presentation reads

The authorized Windows peer test was repeated with redacted field-shape capture. Codex 0.170.0 sent `thread/read` with the exact UUID. Its `thread/resume` request used the exact UUID and `excludeTurns: true`. All 15 optional override values were null. The frontend still rendered the synthetic history and the probe observed the process and transport exit.

The internal request parser recognizes these two method shapes. It returns a typed read or view initialization intent, with a flag for reading turns. It requires the complete, canonical UUID already selected by the owner. It rejects aliases, sibling IDs, extra fields, and non-null context overrides. View initialization uses a distinct internal intent with no native resume method attached. Engine discovery and productive methods have no route through this parser.

The parser and broker passed 31 focused tests. Ruff and strict Twine checks passed. The wheel module matches the source byte for byte.

This code adds no migration and changes no public attachment capability. A transport still has to authenticate the operator and current presenter, apply the exact owner proof, produce bounded and redacted thread responses, and arbitrate authorized effects outside this read parser. The preceding schema-180 build can be restored without data conversion.
