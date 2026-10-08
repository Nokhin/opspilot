---
document_id: POL-REC-001
title: Service Recovery Procedure
version: 1.0
effective_date: 2026-07-01
owner: Digital Services
policy_type: recovery
status: active
---

# Service Recovery Procedure

## 1. Initial containment
The recovery owner confirms affected services and sites, separates observed facts from hypotheses, and protects customers from further disruption. The coordinator records discovery, containment and restoration times separately. Prefer a documented reversible workaround to an untested production change. Before a recovery change, the owner records the change reference and rollback plan using the existing change process. This procedure does not authorise an assistant to execute changes. Classify impact using POL-INC-001 and notify required owners under POL-INC-002.

## 2. Restoration and observation
After service restoration, observe a SEV1 service for at least 30 minutes and a SEV2 service for at least 15 minutes before recommending resolution. Check transaction success, error rate and the affected customer journey against the normal baseline. A single successful request is not sufficient evidence of stable recovery. Record the observation window and owner. If errors recur, continue the incident and notify the coordinator; do not reset downtime to hide recurring interruption. Customer notices must distinguish restored service from completed investigation.

## 3. Reconciliation and integrity
For payment or data-integrity incidents, the recovery owner and Risk & Compliance reconcile affected records before asserting that integrity is restored. Record missing, duplicate and corrected-record counts without placing personal data in public updates. Preserve an original evidence snapshot before any human-approved correction. A service can be technically available while integrity work remains open. Unknown integrity impact must be a limitation in the incident report. Payment-specific containment follows POL-PAY-001; evidence access and retention follow POL-EVD-001.

## 4. Resolution decision
The service owner recommends resolution only after the observation window, impact assessment, required reconciliation and customer update are complete. The Operations Duty Manager confirms the decision for SEV1 and SEV2. Record resolution timestamp, validated service checks, outstanding tasks and resolution summary. An assistant can describe these prerequisites but cannot set the incident status. A root cause may remain provisional at restoration, provided a named owner and review deadline are recorded. Never equate technical availability with an automatic business closure.

## 5. Recovery metrics
Downtime means measured service unavailability. Recovery time from opened_at to resolved_at can include investigation and observation; it is a different metric. Historical mean, median and p90 downtime must disclose category, severity, service and time-window filters. Exclude unknown downtime from duration calculations and report the sample denominator and missing count. Open incidents may have no final downtime. Customer-impact totals are additive incident exposures and are not deduplicated people. Historical duration is context, not a service-level promise.

## 6. Continuity and review
If the interruption persists or safe operation is unavailable, assess POL-BCP-001 continuity criteria with Operations. Continue POL-COM-001 customer updates while restoring service. After resolution, apply POL-REV-001 review criteria and retain the timeline, checks and change references under POL-EVD-001. The owner assigns outstanding actions with deadlines; recommendations remain subject to the relevant human approval process. This procedure applies to the fictional operational environment and does not prescribe vendor-specific commands, infrastructure credentials or unrestricted recovery automation.
