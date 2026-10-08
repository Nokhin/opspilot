---
document_id: POL-PAY-001
title: Payment Service Incident Playbook
version: 1.0
effective_date: 2026-07-01
owner: Digital Services
policy_type: payment
status: active
---

# Payment Service Incident Playbook

## 1. Payment triage
Determine whether the failure is an availability outage, failed authorisation, duplicate capture, delayed settlement or reconciliation mismatch. Record the payment service, observed start time and affected transaction cohort using sanitised references. Do not equate every failed transaction with a unique affected customer. Classify under POL-INC-001: a payment outage lasting at least 30 minutes or affecting at least 500 customers is SEV1, and confirmed duplicate capture is at least SEV2. Escalation is required before root cause is confirmed.

## 2. Duplicate payment containment
For suspected duplicate capture, ask the recovery owner to assess safe containment and preserve original transaction evidence. Do not recommend repeated manual payment retries while duplicate capture is unresolved. An approved human operator decides whether to disable an affected flow using the existing change process. The assistant cannot reverse charges, submit payments, issue refunds or alter records. Inform Risk & Compliance and the Customer Service Lead within the relevant POL-INC-002 deadline. Vendor-related symptoms additionally follow POL-VEN-001.

## 3. Reconciliation checks
The recovery owner compares authorised, captured, settled and recorded transactions for the affected time window. Record missing or duplicate counts and the reconciliation source. Keep original and corrected evidence distinct. Risk & Compliance reviews material integrity differences before the service owner declares reconciliation complete. An unknown financial impact remains unknown; do not calculate a cash total from customer count alone. The corpus does not define a per-customer refund, compensation amount, universal credit or supplier penalty.

## 4. Safe customer guidance
Customer messages state affected payment functionality, available approved alternatives and the next update time. Tell customers how to seek individual transaction review through Customer Service without exposing payment details. Do not promise successful retry, reimbursement or a restoration time without a confirmed basis. Use POL-COM-001 first-notice and update cadence. A supplier outage announcement can be supplementary context but is not proof of HarbourLink transaction integrity or permission to replace an internal procedure with external guidance.

## 5. Recovery confirmation
After restoration, validate the full payment journey and reconciliation, then observe SEV1 service for 30 minutes or SEV2 for 15 minutes under POL-REC-001. The recovery owner records checks and outstanding integrity work. The Operations Duty Manager confirms resolution for SEV1 and SEV2; no assistant can close the incident. If interruption reaches 60 minutes, assess continuity under POL-BCP-001 while maintaining escalation and customer updates. Historical downtime comparisons must disclose the matching filters and missing-duration denominator.

## 6. Review and prevention
Every confirmed payment-integrity incident requires a POL-REV-001 review even if its customer count is low. Include detection controls, containment decisions, reconciliation method, supplier response and customer notices. Preserve evidence for 180 days after resolution under POL-EVD-001, unless a legal hold extends retention. Recommendations should identify a control weakness supported by evidence rather than a vendor command or assumed financial entitlement. The fictional playbook supplies operational criteria, not production payment credentials or permission to execute transactions.
