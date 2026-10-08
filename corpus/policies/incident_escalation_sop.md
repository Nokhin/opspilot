---
document_id: POL-INC-002
title: Incident Escalation SOP
version: 1.0
effective_date: 2026-07-01
owner: Operations
policy_type: escalation
status: active
---

# Incident Escalation SOP

## 1. Trigger and notification clock
Escalation begins when an incident meets a severity threshold in POL-INC-001. The analyst records when the threshold was first detected and uses that time for notification deadlines. Escalation is a human action: an assistant may recommend recipients and prepare a draft, but a responsible employee sends the notification. A failed delivery does not satisfy the deadline. Record recipient, channel, sent time and acknowledgement. Use the on-call contact directory; this corpus does not contain phone numbers or personal contact details.

## 2. Severity 1 notification
For a Severity 1 (SEV1) incident, notify the Operations Duty Manager and the relevant recovery team within 5 minutes of threshold detection. Notify the Customer Service Lead within 10 minutes, Risk & Compliance within 15 minutes, and the Executive Duty Sponsor within 30 minutes. Digital Services is the recovery team for digital or payment outages; Facilities is the recovery team for physical disruption. The Duty Manager appoints an incident coordinator and opens a coordination bridge. Do not wait for root-cause confirmation before these notifications.

## 3. Severity 2 and lower notification
For Severity 2 (SEV2), notify the Operations Duty Manager and recovery team within 15 minutes, and the Customer Service Lead within 30 minutes. Risk & Compliance must be included within 30 minutes when integrity, safety or suspected data loss is involved. SEV3 and SEV4 are managed by the assigned service owner during the operating shift; record the handover if unresolved. If any SEV1 threshold develops, start the SEV1 clock at that threshold detection and record the upgrade. Lower severity never permits bypassing evidence preservation.

## 4. Missing acknowledgement
If the primary recovery owner has not acknowledged a SEV1 notification within 5 minutes of sending, contact the alternate on-call owner and inform the Duty Manager. For SEV2, use the alternate after 15 minutes without acknowledgement. Keep both attempts in the incident timeline. The coordinator continues customer-impact assessment while seeking an owner. Do not expose customer-identifying records in a general coordination channel. Supplier acknowledgements are managed under POL-VEN-001 and do not replace internal escalation or ownership.

## 5. Escalation content and boundaries
A notification includes incident ID, severity and triggering facts, affected services/sites, discovery time, elapsed downtime, known or estimated customer impact, recovery owner, current actions and next update time. State uncertainty explicitly. Historical median downtime can support a planning discussion but is not a recovery promise or permission to delay escalation. An escalation draft must be visibly marked as unsent. An AI assistant must never create, close or change incident records, send notifications, or change business state in this V1 demonstration.

## 6. Handover and related procedures
The coordinator maintains a chronological action log, confirms an owner for every open task, and records the next checkpoint. At shift change, the outgoing and incoming coordinators acknowledge the handover. Customer updates follow POL-COM-001, recovery checks follow POL-REC-001, supplier escalation follows POL-VEN-001, and continuity activation follows POL-BCP-001. Preserve all relevant evidence under POL-EVD-001. Final resolution does not remove the review obligation in POL-REV-001. This SOP does not grant compensation approval or define any cash entitlement.
