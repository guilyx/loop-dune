-- Minimal Loop dataset for the backup round-trip test (CI). Apply after migrations.
insert into loop.markets (market_id, name, chain, chain_id, underlying_symbol, underlying_address,
    underlying_decimals, pool_address, pool_symbol, start_block)
values ('tst', 'Loop TST', 'testnet', 31337, 'TST', '0x00000000000000000000000000000000000000a1',
    6, '0x00000000000000000000000000000000000000b1', 'lpTST', 100);

insert into loop.series (series_id, chain, chain_id, market_id, entity_type, entity_id, metric,
    contract_address, function_signature, decimals, unit, description, active_from_block)
values ('tst.pool.expected_liquidity', 'testnet', 31337, 'tst', 'pool', 'pool',
    'expected_liquidity', '0x00000000000000000000000000000000000000b1', 'expectedLiquidity()',
    6, 'TST', 'test series', 100);

insert into loop.snapshots (chain_id, ts, block_number, block_timestamp, series_count)
select 31337, ts, 1000 + n, ts - interval '5 seconds', 1
from generate_series(1, 48) as n, lateral (select timestamptz '2025-01-01' + n * interval '1 hour' as ts) t;

insert into loop.observations (series_id, ts, block_number, raw, value)
select 'tst.pool.expected_liquidity', ts, block_number, block_number * 1000000, block_number
from loop.snapshots;
