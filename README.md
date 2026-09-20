# MonashHack

Email classification and shipping-document verification project.

## Participant data

Use `download2/` as the application input. The original inbox and attachment
files are immutable. The ignored `download/` directory contains evaluator-only
material and must never be used by the production pipeline.

## Validate the inbox

Run the Step 2 read-only validator with the project Python environment:

```powershell
.\.venv\Scripts\python.exe scripts\validate_inbox.py download2
```

The command validates email fields, IDs, attachment paths, and local attachment
existence, then prints a JSON dataset summary. It does not classify messages or
read attachment contents.

## Classification output contract

Later classification steps will write generated records under
`outputs/usable/` and `outputs/unusable/`; source records will not be moved.
The internal categories will be `bl_comparison`, `spam`, `general_message`,
`invoice_query`, and `new_si_request`. The official submission adapter will map
these values to the competition's required category names.
