# Labeling and Split Design

## Scope

Step 3 creates a reproducible, leakage-safe annotation and evaluation split for
the 520 participant emails. The active classification strategy is Rules + LLM,
so this step does not train a supervised model.

The split contains:

- 120 emails selected for human annotation;
- 80 annotated emails used for development and validation;
- 40 annotated emails reserved as a locked final test set;
- 400 remaining emails processed by the final production system.

## Data Boundary

- Read only from `download2/inbox/` and attachment metadata referenced there.
- Never read `download/`, `ground_truth*.json`, evaluator code, or submission
  feedback.
- Keep every original inbox JSON and attachment unchanged.
- Store generated manifests and human labels separately under `data/splits/`.
- Store email IDs and split metadata in manifests instead of copying source
  emails into split directories.

## Internal Categories

Human labels use exactly these internal values:

- `bl_comparison`
- `new_si_request`
- `invoice_query`
- `general_message`
- `spam`

The Step 9 submission adapter will map them to the competition category names.

## Two-Stage Process

### Stage A: Annotation pool selection

Before labels exist, select a deterministic 120-email annotation pool and place
the other 400 emails in the production manifest. Use a fixed seed recorded in
the manifest.

Selection must not infer private answers. It may use observable input structure
to improve coverage, including attachment pattern, attachment extensions,
missing text, body length bands, and duplicate/template groups.

Exact duplicates and template-related emails must share one stable `group_id`.
No group may cross between the annotation pool and production. Selection should
cover the observed attachment patterns while meeting the exact 120/400 sizes.

Outputs:

- `data/splits/annotation_pool.json`
- `data/splits/production.json`
- `data/splits/annotations.csv`

The annotation CSV contains `email_id`, an initially empty `category`, and an
optional `notes` column. It must not prefill a category from heuristics, rules,
the sample submission, or evaluator-only data.

### Stage B: Development and final-test split

Stage B runs only after all 120 annotation rows contain a valid human category.
Create an exact 80/40 split using group-aware, category-stratified assignment.
No duplicate/template group may cross between development and final test.

The split optimizer should minimize category-distribution differences while
meeting exact sizes. If exact group-aware stratification is impossible, stop
with a clear diagnostic instead of breaking a group.

Outputs:

- `data/splits/development.json`
- `data/splits/final_test.json`

Development labels may be used to adjust rules, prompts, routing, and human
review criteria. Final-test labels are evaluation-only and must not be imported
by production classification modules.

## Duplicate and Template Groups

Use normalized subject and body text to identify exact duplicates. Build a
second conservative template signature by lowercasing, normalizing whitespace,
and replacing email addresses, URLs, and numeric tokens with placeholders.

Records sharing either an exact signature or a template signature belong to the
same connected group. Stable group IDs derive from a hash of sorted email IDs,
not from Python's process-randomized `hash()` function.

This grouping is intentionally conservative. It prevents known repeated spam,
operational templates, and date/number variants from crossing split boundaries.

## Manifest Format

Each JSON manifest contains metadata and records:

```json
{
  "schema_version": 1,
  "seed": 20260921,
  "split": "annotation_pool",
  "records": [
    {
      "email_id": "email_001",
      "group_id": "group_ab12cd34",
      "attachment_pattern": "si_bl"
    }
  ]
}
```

Records are sorted by `email_id`. Manifests contain no email body, prediction,
private answer, or final-test label.

## Commands

Provide one script with two explicit operations:

```powershell
.\.venv\Scripts\python.exe scripts\prepare_splits.py select download2 data\splits
.\.venv\Scripts\python.exe scripts\prepare_splits.py finalize data\splits
```

`select` creates Stage A outputs. It refuses to overwrite existing manifests
unless they are byte-for-byte reproducible from the same inputs and seed.

`finalize` validates every annotation row, verifies the ID set and allowed
categories, then creates Stage B outputs. It never changes the annotation CSV.

## Error Handling

Stop with a non-zero exit code and a clear reason for:

- missing, duplicate, or unknown annotation IDs;
- empty or invalid categories during finalization;
- changed source ID sets;
- a duplicate group crossing an existing boundary;
- inability to meet exact 120/400 or 80/40 sizes without splitting a group;
- a path pointing to evaluator-only material;
- malformed or incompatible manifests.

Partial output files must not be left behind after failure. Write each completed
artifact atomically through a temporary file in the destination directory.

## Testing and Acceptance

Automated tests must verify:

- deterministic output for seed `20260921`;
- exact 120/400 Stage A sizes;
- exact 80/40 Stage B sizes after valid labels are supplied;
- no ID overlap and complete coverage of all 520 emails;
- no group crosses any forbidden boundary;
- annotation CSV starts with empty categories;
- invalid or incomplete labels prevent finalization;
- evaluator-like paths are rejected;
- original participant files remain unchanged.

Step 3 is complete only after Stage A outputs are generated and verified. Stage
B remains intentionally pending until humans finish all 120 labels.
