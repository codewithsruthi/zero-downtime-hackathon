BLUEPRINTS = [
    {
        "identifier": "hydra_source",
        "title": "HYDRA Data Source",
        "icon": "Database",
        "schema": {
            "properties": {
                "kind": {
                    "type": "string",
                    "enum": ["web_page", "json_api", "csv_file", "structured_feed"],
                },
                "url": {"type": "string", "format": "url"},
                "contract_version": {"type": "number"},
                "health": {
                    "type": "string",
                    "enum": ["healthy", "degraded", "failed", "healing"],
                },
                "circuit_state": {
                    "type": "string",
                    "enum": ["closed", "half_open", "open"],
                },
                "freshness_seconds": {"type": "number"},
                "freshness_slo_seconds": {"type": "number"},
                "acquisition_rung": {"type": "number"},
                "autonomy_tier_max": {"type": "number"},
                "assertion_count": {"type": "number"},
                "last_run_status": {"type": "string"},
                "heals_last_7d": {"type": "number"},
                "owner_team": {"type": "string"},
            },
            "required": ["kind", "health", "contract_version"],
        },
    },
    {
        "identifier": "hydra_run",
        "title": "HYDRA Run",
        "icon": "Clock",
        "schema": {
            "properties": {
                "status": {"type": "string"},
                "rows_in": {"type": "number"},
                "rows_out": {"type": "number"},
                "duration_ms": {"type": "number"},
                "trace_id": {"type": "string"},
            },
            "required": ["status"],
        },
        "relations": {"source": {"target": "hydra_source", "required": True, "many": False}},
    },
    {
        "identifier": "hydra_incident",
        "title": "HYDRA Incident",
        "icon": "Alert",
        "schema": {
            "properties": {
                "failure_class": {
                    "type": "string",
                    "enum": ["F1", "F2", "F3", "F4", "F5", "F6"],
                },
                "fingerprint": {"type": "string"},
                "detected_at": {"type": "string", "format": "date-time"},
                "resolved_at": {"type": "string", "format": "date-time"},
                "mttd_seconds": {"type": "number"},
                "mttr_seconds": {"type": "number"},
                "resolution": {
                    "type": "string",
                    "enum": ["healed", "escalated", "blocked", "open"],
                },
                "attempts": {"type": "number"},
                "trace_id": {"type": "string"},
                "evidence": {"type": "string", "format": "markdown"},
            },
            "required": ["failure_class", "fingerprint", "detected_at"],
        },
        "relations": {"source": {"target": "hydra_source", "required": True, "many": False}},
    },
    {
        "identifier": "hydra_heal_action",
        "title": "HYDRA Heal Action",
        "icon": "Bolt",
        "schema": {
            "properties": {
                "primitive": {
                    "type": "string",
                    "enum": ["P1", "P2", "P3", "P4", "P5", "P6", "P7", "P8"],
                },
                "autonomy_tier": {"type": "number"},
                "attempt": {"type": "number"},
                "approved_by": {"type": "string"},
                "verification_passed": {"type": "boolean"},
                "duration_seconds": {"type": "number"},
                "before_state": {"type": "string", "format": "markdown"},
                "after_state": {"type": "string", "format": "markdown"},
            },
            "required": ["primitive", "autonomy_tier"],
        },
        "relations": {
            "incident": {"target": "hydra_incident", "required": True, "many": False}
        },
    },
    {
        "identifier": "hydra_heal_pattern",
        "title": "HYDRA Heal Pattern",
        "icon": "Star",
        "schema": {
            "properties": {
                "failure_class": {"type": "string"},
                "successful_primitive": {"type": "string"},
                "occurrences": {"type": "number"},
                "avg_mttr_seconds": {"type": "number"},
            },
            "required": ["successful_primitive"],
        },
    },
]

SCORECARD = {
    "identifier": "hydra_self_healing_maturity",
    "title": "Self-Healing Maturity",
    "blueprint": "hydra_source",
    "rules": [
        {
            "identifier": "has_contract",
            "title": "Has a contract with at least 3 assertions",
            "level": "Bronze",
            "query": {
                "combinator": "and",
                "conditions": [{"property": "assertion_count", "operator": ">=", "value": 3}],
            },
        },
        {
            "identifier": "telemetry_and_freshness",
            "title": "Telemetry flowing and inside freshness SLO",
            "level": "Silver",
            "query": {
                "combinator": "and",
                "conditions": [
                    {"property": "is_stale", "operator": "=", "value": False},
                    {"property": "last_run_status", "operator": "=", "value": "ok"},
                ],
            },
        },
        {
            "identifier": "proven_autonomous_heal",
            "title": "At least one verified autonomous heal in 7 days",
            "level": "Gold",
            "query": {
                "combinator": "and",
                "conditions": [
                    {"property": "heals_last_7d", "operator": ">=", "value": 1},
                    {"property": "circuit_state", "operator": "=", "value": "closed"},
                ],
            },
        },
    ],
}


async def bootstrap_port(pool) -> None:
    for blueprint in BLUEPRINTS:
        await pool.invoke("catalog_upsert_blueprint", **blueprint)
    await pool.invoke("scorecard_upsert", **SCORECARD)
