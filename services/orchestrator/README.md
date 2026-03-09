# Orchestrator

Deterministic state machine: project state, job dispatch, retries.
State: draft → floorplan_ingested → plan_parsed → graph_built → style_inferred → geometry_rules_built → model_reconstructed → model_critiqued → renders_generated → exports_ready → ready
