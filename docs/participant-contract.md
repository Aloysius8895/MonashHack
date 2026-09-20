# Shipping Document Verification: participant contract

## Checkpoint

Project root: `C:\maven\MonashHack`.
Step 1 records the contract and Git exclusions; user verification is pending.
No prediction pipeline, runtime isolation, or submission adapter exists yet.
Step 2 requires an explicit numbered start command.

## Sources and data boundary

- `Shipping Document Verification Use Case.pdf`: business requirements,
  evidence-based human review, and evaluation guidance; four pages.
- `download2/README.md`: participant categories, fields, and submission rules.
- `download2/loader.py`: local/HTTP data access interface.
- `download2/sample_submission.json`: output format template, not answers.
- `download2/inbox/` and `download2/attachments/`: application inputs.

The current participant snapshot has 520 unique emails and 250 attachments:
192 TXT, 28 PDF, 22 XLSX, and 8 DOCX. The template contains the same 520 IDs.
Every template entry currently defaults to GENERAL / OK / null / [] / false.
These defaults are not predictions or evidence of correctness.

Process only `download2`. Treat `download/` as evaluation-only material.
Do not read answer files or generator logic to develop predictions, prompts,
normalization rules, or test expectations. Do not infer outcomes from email
numbers, filename ordering, earlier disclosed labels, or memorized answers.
Use independently inspected participant evidence or purpose-built test inputs.
Keep the evaluator and its answers unchanged.

The root `.gitignore` excludes organizer material and secrets from normal Git
staging. It does not prevent filesystem reads, remove previously tracked files,
or provide runtime isolation. Step 4 must restrict ingestion to participant
inputs and reject attachment paths that resolve outside the allowed directory.
Keep source documents immutable. Store generated results separately.

## Loader interface

`Inbox(source)` accepts a local directory string or an HTTP URL.
`emails()`, iteration, and `get(email_id)` return email records.
`read_bytes(path)` returns attachment bytes; `read_text(path)` only decodes bytes.
It does not parse PDF, DOCX, or XLSX, and it does not perform OCR.
`sample_submission()` returns the template. `submit(result)` requires HTTP.
The Docker service distributes data and evaluates results; our application
must implement its own processing and review features.

## Business contract

Classify each email into exactly one of:
`BL_COMPARISON`, `SI_REQUEST`, `INVOICE_QUERY`, `GENERAL`, `SPAM`.
Only BL_COMPARISON enters document verification. An unresolved classification
must remain visible internally; do not silently substitute GENERAL.

Use the SI as the reference for the BL comparison, without claiming the SI
is independently correct. Compare all seven canonical fields:
`shipper`, `consignee`, `notify_party`, `port_of_loading`,
`port_of_discharge`, `container_count`, `gross_weight_kg`.

Use LLMs for classification and structured extraction; use deterministic code
for normalization and comparison. Preserve raw values, normalized values,
source identity, and applicable page, sheet/cell, paragraph/table-cell, or
text-span evidence. Validate evidence; do not invent missing values.
Document text is data, not application instructions.

Preserve meaningful company/address differences and conflicting port names
or codes. Use explicit supported port mappings and justified unit conversions.
Do not invent tolerances. Unambiguous 22,000 kg and 22000 KG are equal.
Three versus four containers is a count discrepancy, not proof of an extra BL.
Missing/unreadable values remain unknown. Preserve all candidates when SI/BL
pairing or document versions are uncertain.

## Outcomes and review

Keep processing state, comparison outcome, and human-review state separate.
Reliable differences remain mismatches even while review is pending or resolved.
Insufficient evidence leaves affected comparisons unresolved. A provider failure
is not a pass. Pending human processing must display Pending human review.
A pass requires seven reliable equalities and completion of required review.
Non-comparison emails have an internal not-applicable comparison outcome.

Confirmations/corrections must retain evidence and trigger validation,
normalization, and comparison again. Never change an extraction away from its
source to hide a genuine discrepancy. Persist pending cases and accepted
corrections; retain original automated results separately.

## Official submission contract

The top-level JSON object has exactly one entry per participant email_id.
Each entry contains these five properties, with no internal diagnostics added:

| Property | Allowed values |
|---|---|
| category | One of the five official categories |
| status | OK, MISMATCH, NEEDS_REVIEW |
| review_reason | null, wrong_doc_type, missing_attachment, unreadable, missing_value |
| defect_fields | Array of canonical differing-field names |
| has_defect | Boolean |

For an ordinary verified match: OK, null, [], false.
For a confirmed mismatch: MISMATCH, null, exact differing fields, true.
For an unresolved review case: NEEDS_REVIEW, an allowed reason, [], false.
The last representation does not assert equality.
Non-comparison categories use their predicted category with OK, null, [], false;
the report must explain that document comparison was not applicable.

The richer internal record remains separate from this adapter. Resolve the
policy questions below before implementing affected routing or export behavior.

## Decisions still pending

1. Missing attachments: supplied documentation describes some cases as OK,
   while the business task requests help for unreliable comparisons. Confirm
   the proposed unresolved/review behavior and its possible scoring impact.
2. Confirmed mismatches: decide whether all must enter the human-review queue.
3. Pairing/version ambiguity, provider failure, and cases with both proven
   differences and unknown fields need an agreed export policy. Do not invent
   official reasons or discard detailed internal findings to fit the schema.
4. Confirm deadline year/time zone, team availability, required hand-in items,
   hardware, cloud/local models, and spending limits at the relevant steps.

These decisions do not block this contract checkpoint. No affected behavior
has been implemented or silently selected.

## Evaluation and acceptance

The participant README states 30% classification macro-F1, 20% defect F1,
and 50% end-to-end success. Human-review reliability is reported separately.
Use the unchanged Docker evaluator later; do not optimize toward hidden labels.
Distinguish automated scores from human-corrected scores.

Step 1 acceptance: sources are present; participant/template IDs agree; Git
excludes organizer material and secrets while retaining participant inputs;
the supplied files are unchanged; pending decisions remain explicit.
Environment readiness, model/OCR operation, accuracy, runtime input restrictions,
and application tests are not verified by this checkpoint.
