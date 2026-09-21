# Module Architecture

Three workstreams build in parallel on separate branches. They must not import
each other. The only shared dependency is `src/contracts/`.

```
                    +---------------------+
                    |    src/contracts    |   schemas, handoff files, ports
                    +---------------------+   (depends on nothing)
                       ^      ^      ^
        +--------------+      |      +--------------+
        |                     |                     |
+-------+---------+  +--------+----------+  +-------+--------+
| email_          |  | document_         |  | verification   |
| classification  |  | extraction        |  |                |
+-----------------+  +-------------------+  +----------------+
   feature/email-      feature/document-      feature/
   classification      extraction             verification

                    +---------------------+
                    |    src/pipeline     |   wires the ports together
                    +---------------------+   (depends on contracts only)
```

## The rule

`tests/test_module_boundaries.py` enforces this by parsing every import in
`src/`. A module may import `contracts` and its own submodules. Nothing else.
If you add a package under `src/`, declare its allowed dependencies in that
test or the suite fails.

This is why `src/pipeline/orchestrator.py` receives an extractor and a verifier
as arguments instead of importing them: the orchestrator knows the ports, never
the implementations.

## Stage handoff

Stages communicate through JSON files, not function calls. A stage can be run,
re-run, or replaced without the others being present.

| Stage | Writes | Reads |
| --- | --- | --- |
| classification | `outputs/handoff/classification.json` | the inbox bundle |
| extraction | `outputs/handoff/extraction.json` | classification handoff |
| verification | `outputs/handoff/verification.json` | extraction handoff |

Every handoff file carries `schema_version` and `stage`, and `read_handoff`
rejects a file whose version or stage does not match what the caller expects.
Attachment paths in the classification handoff are relative to the inbox bundle
root (`download2/`), so they stay valid across machines.

## Owning a stage

`src/document_extraction/` and `src/verification/` currently hold the interface
and raise `ExtractionUnavailable` / `VerificationUnavailable`. The orchestrator
turns either into a `not_verified` result with `review_required`, so the
pipeline runs end to end today and degrades to human review for the stages that
are not built yet.

To implement a stage:

1. Fill in `extract()` or `verify()` in your own package. Do not touch another
   package.
2. Return the contract dataclass. Raise the matching `*Unavailable` error for
   anything you cannot process, rather than returning a partial result.
3. Add tests under `tests/`; use stub ports rather than the real neighbours.

## Category names

`email_classification` uses internal category names (`bl_comparison`, ...).
`contracts` uses the published names (`document_comparison`, ...).
`email_classification/contract_adapter.py` is the only place that translates,
so the internal vocabulary can change without touching downstream modules.
