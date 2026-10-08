---
document_id: POL-INC-001
title: Incident Classification Standard
version: 1.0
effective_date: 2026-07-01
owner: Risk & Compliance
policy_type: classification
status: active
---

# Incident Classification Standard

## 1. Scope and recording
HarbourLink Services classifies disruptions affecting customer centres, online services, payments, facilities and operational records. An incident is an unplanned service interruption or integrity failure that needs coordinated response. The recorder captures discovery time, affected service and site, observed impact, current owner and unknown facts. A service request without disruption is not an incident. The incident record must label estimated values as estimates; an unknown impact must not be recorded as zero. One incident may affect multiple functions but has one coordinating owner.

## 2. Severity 1 thresholds
Severity 1 (SEV1) applies when at least 500 customers are affected, when a customer-facing digital or payment service is continuously unavailable for 30 minutes or longer, or when there is credible immediate danger to people. A multi-site closure that prevents essential customer service is also SEV1. Any one threshold is sufficient. An outage lasting 35 or 45 minutes therefore meets the duration threshold even if the impact count is unknown. Suspected impact is validated urgently; classification is precautionary while safety facts are uncertain. Escalation is defined in POL-INC-002 section 2.

## 3. Severity 2, 3 and 4
Severity 2 (SEV2) applies to 100–499 affected customers, a customer-facing outage of 10–29 minutes, or a single-site disruption without immediate danger. Confirmed duplicate payment capture is at least SEV2, regardless of initial count. Severity 3 (SEV3) is a local degradation affecting fewer than 100 customers with a workaround and no safety or financial-integrity concern. Severity 4 (SEV4) is a minor operational defect with no current customer interruption. If a higher threshold is reached, the higher severity takes priority over these examples.

## 4. Classification review
The Operations Duty Manager reviews severity at discovery and whenever impact, duration or safety changes. Escalation clocks start when the relevant threshold is detected, not when a form is completed. Record the previous classification, new classification, observed trigger and timestamp when severity changes. Never lower severity solely to meet a reporting target. Downgrade only after the Duty Manager confirms stable service and bounded impact. The response requirements for the highest observed severity remain part of the post-incident review record.

## 5. Ownership and uncertainty
Digital Services owns digital recovery; Facilities owns site equipment and physical hazards; Customer Service owns outbound customer updates; Risk & Compliance advises on integrity and evidence handling. Operations coordinates across these owners. A vendor-related cause does not transfer accountability away from HarbourLink. If the affected service is unclear, assign Operations as temporary owner and record the uncertainty. Ownership is confirmed during triage rather than inferred from an incident category alone. Historical incident averages are context and do not change severity thresholds.

## 6. Linked standards and records
Use POL-INC-002 for notification deadlines, POL-COM-001 for customer communications and POL-REV-001 for review requirements. Record the exact classification trigger, including elapsed downtime and impact estimate, so another analyst can reproduce the decision. Keep evidence according to POL-EVD-001. This fictional standard defines internal operational classification only. It does not establish regulatory obligations or substitute for professional safety assessment. Historical incidents before the effective date are not automatically subject to this version; retrospective analysis must state that limitation.
