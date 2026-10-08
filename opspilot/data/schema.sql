CREATE TABLE incidents (
    incident_id TEXT PRIMARY KEY CHECK (incident_id GLOB 'INC-[0-9][0-9][0-9]'),
    opened_at TEXT NOT NULL CHECK (julianday(opened_at) IS NOT NULL AND substr(opened_at,-1)='Z'),
    resolved_at TEXT CHECK (resolved_at IS NULL OR
        (julianday(resolved_at) IS NOT NULL AND substr(resolved_at,-1)='Z'
         AND julianday(resolved_at)>=julianday(opened_at))),
    category TEXT NOT NULL CHECK (category IN ('digital_outage','payment_failure',
        'facility_disruption','customer_impact','data_integrity','vendor_disruption')),
    subcategory TEXT NOT NULL,
    severity TEXT NOT NULL CHECK (severity IN ('SEV1','SEV2','SEV3','SEV4')),
    business_unit TEXT NOT NULL CHECK (business_unit IN ('Operations','Customer Service',
        'Digital Services','Facilities','Risk & Compliance')),
    service TEXT NOT NULL,
    site TEXT NOT NULL,
    customer_impact_count INTEGER NOT NULL CHECK (
        typeof(customer_impact_count)='integer' AND customer_impact_count>=0),
    downtime_minutes INTEGER CHECK (downtime_minutes IS NULL OR
        (typeof(downtime_minutes)='integer' AND downtime_minutes>=0)),
    estimated_cost REAL CHECK (estimated_cost IS NULL OR estimated_cost>=0),
    root_cause TEXT,
    vendor_related INTEGER NOT NULL CHECK (vendor_related IN (0,1)),
    status TEXT NOT NULL CHECK (status IN ('open','investigating','resolved')),
    resolution_summary TEXT,
    post_incident_review_required INTEGER NOT NULL CHECK (post_incident_review_required IN (0,1)),
    CHECK ((status='resolved' AND resolved_at IS NOT NULL) OR
           (status IN ('open','investigating') AND resolved_at IS NULL))
);
CREATE INDEX incident_opened_idx ON incidents(opened_at);
CREATE TABLE dataset_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
