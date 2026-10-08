# Golden set provenance

50 authored English cases; expected policy sections and reference points were labelled from the corpus before the first evaluation. Numeric constants were frozen from independent SQLite reads with julianday time comparisons and Python arithmetic, without using IncidentRepository or its metrics implementation. Dataset hash: `734cb1b898b986bd70a1532a8f042fc97cf594b5a281fcc0c7635ab7d8ed78b8`. Changing the generator requires reviewing those constants; the runner never regenerates expected values. The suite is a regression set, not a representative real-enterprise benchmark or held-out semantic evaluation.

## Clarification after the first completed live run

The legacy `opspilot/evaluation/cases.json` is preserved byte-for-byte (SHA-256
`02f648f314b1dd0789d02ab95a6a7ea080a4c987ce4ede5e267ddee87a3c178a`).
The completed legacy live run passed 47/50. `mixed_07` asked for SEV1 policy and
"severity distribution of incidents", but the numeric label describes only SEV1
incidents. The model returned the all-severity distribution, a defensible reading
of that ambiguous question; its original failed grade remains in the report.

The default dataset revision `cases_v1_1.json` changes only `mixed_07.question`:
"severity distribution of incidents" becomes "severity distribution of SEV1 incidents".
All routes, expected tools, source/section labels, numeric constants and other
49 questions are unchanged. This makes the question agree with its independently
labelled cohort; it does not change the expected numbers to match model output.
New case-file hash:
`e3310ab655fdb8fe45a553fadf2fe220364f370ec4c7e2be9a2d0c67e7179ef1`.
Reports carry the input hash and both dataset versions remain runnable using `--cases`.
This is a dataset clarification, not held-out evaluation or a new application release.
