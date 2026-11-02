-- Loop: de-duplicated observations
-- Save as a Dune query and reference it from the others as query_<id>, or inline it.
--
-- Parameters: {{namespace}} (text) - the Dune namespace the indexer uploads to
--             (DUNE_NAMESPACE).
--
-- Delivery to Dune is at-least-once, and re-sampled hours are re-sent, so keep the
-- most recently ingested row per (series_id, ts).
select
    ts,
    chain_id,
    block_number,
    market_id,
    entity_type,
    entity_id,
    metric,
    series_id,
    unit,
    value,
    cast(raw_value as uint256) as raw_value,
    ingested_at
from (
    select
        o.*,
        row_number() over (partition by series_id, ts order by ingested_at desc) as rn
    from dune.{{namespace}}.loop_observations as o
)
where rn = 1
