---
document_id: POL-REV-001
title: Post-Incident Review Standard
version: 1.0
effective_date: 2026-07-01
owner: Risk & Compliance
policy_type: review
status: active
---

# Post-Incident Review Standard

## 1. Mandatory review criteria
A post-incident review is required for every SEV1 incident, every confirmed payment or data-integrity incident, and a service with three or more similar incidents in a rolling 30-day period. The Operations Duty Manager can also require a review for a lower-severity event with important learning. Similar incidents share a service and failure category; matching a broad business unit alone is insufficient. A review-required flag in the historical database records that dataset's classification and is not proof that the review was completed.

## 2. Review timetable
The incident coordinator schedules a SEV1 review within 2 business days of resolution and publishes the draft review within 5 business days. Business days mean Monday to Friday, excluding HarbourLink's approved holiday calendar; the holiday calendar is not included in this corpus. For other mandatory reviews, schedule within 5 business days and publish the draft within 10 business days. Record owner and due date at resolution. If a deadline cannot be met, the Duty Manager records the exception and revised date.

## 3. Required review content
The review includes a factual timeline, severity triggers, customer impact, downtime and its measurement basis, escalation and communication performance, confirmed root cause or unresolved hypotheses, recovery decisions and evidence references. Compare against the policies effective at the event date where available. Current policies can support learning but cannot prove past compliance for older events. A historical median is context rather than a target. Include missing values and uncertainty instead of replacing unknown facts with plausible estimates.

## 4. Action ownership
Each corrective action has an accountable owner, target date, verification criterion and status tracked through the existing human-managed process. Separate containment work from long-term prevention. Risk & Compliance checks that evidence supports claims and that actions address confirmed contributing factors. The assistant may recommend candidate actions but cannot create tasks, assign owners in a business system or close actions. Avoid individual blame without evidence; focus the review on controls, dependencies and the conditions that produced the outcome.

## 5. Repeat-incident analysis
When checking repeat incidents, apply an explicit opened_at time window, service and category filter. Report count and matching record IDs, including whether records are open or resolved. A sampled list is not an exhaustive recurrence count. The rolling 30-day criterion includes the current event only if it is present in the selected dataset. Do not treat a year-wide repeat count as the 30-day review trigger. For V1, the analyst must explicitly select the window and verify those details before concluding the threshold applies.

## 6. Retention and dissemination
Retain the approved review, timeline and action references for 180 days under POL-EVD-001, subject to any legal hold. Share a sanitised learning summary with the affected functions; restrict customer-identifying evidence to approved investigators. The coordinator links the final review to the incident record through the existing controlled process. Review completion does not itself permit deletion of underlying logs. This fictional standard contains no compensation schedule or statutory reporting rule; absent legal or commercial requirements must be treated as missing evidence.
