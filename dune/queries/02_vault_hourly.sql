-- Loop: one row per (vault, hour). Collateral value and debt in the market's underlying.
-- Mirrors loop.vault_hourly. Parameters: {{namespace}} (text)
with obs as (
    select *
    from (
        select o.*, row_number() over (partition by series_id, ts order by ingested_at desc) as rn
        from dune.{{namespace}}.loop_observations as o
    )
    where rn = 1 and entity_type = 'vault'
),
pivot as (
    select
        ts,
        market_id,
        entity_id as vault_id,
        max(value) filter (where metric = 'collateral_balance') as collateral_balance,
        max(value) filter (where metric = 'spot_price')         as spot_price,
        max(value) filter (where metric = 'total_debt')         as total_debt,
        max(value) filter (where metric = 'debt_ceiling')       as debt_ceiling,
        max(value) filter (where metric = 'pool_borrowed')      as pool_borrowed
    from obs
    group by 1, 2, 3
)
select
    p.ts,
    p.market_id,
    p.vault_id,
    v.name                                  as vault_name,
    v.collateral_symbol,
    p.collateral_balance,
    p.spot_price,
    p.collateral_balance * p.spot_price     as collateral_value,
    p.total_debt,
    p.debt_ceiling,
    p.pool_borrowed,
    if(p.collateral_balance * p.spot_price > 0,
       p.total_debt / (p.collateral_balance * p.spot_price)) as ltv
from pivot as p
left join dune.{{namespace}}.loop_vaults as v
    on v.market_id = p.market_id and v.vault_id = p.vault_id
order by p.market_id, p.vault_id, p.ts
