# MT7/MT8 solve_spread reproduce (Part 3)

stop_rule_held=True

| case | status | pass | spread | rank | distance |
|---|---|---|---|---|---|
| mt7_t1 | optimal | True | Bold 31/0/1/0/29/5 | 2 | 4 |
| mt7_t2 | optimal | True | Bold 31/0/1/0/29/5 | 2 | 4 |
| mt7_t3 | optimal | True | Bold 31/0/1/0/29/5 | 2 | 4 |
| mt8_t3_modest | infeasible | True |  | None | None |
| mt8_t3_timid | optimal | True | Bold 31/0/1/0/29/5 | 2 | 4 |
| mt8_relax_jolly_sneasler | optimal | True | Calm 30/0/1/0/30/5 | 5 | 10 |
| mt8_relax_drop_gate | infeasible | True |  | None | None |

If membership/calc-verify/infeasible match fails by end of 2026-10-28, STOP: fall back to lookup-only arm for MT7/MT8 as dev findings; solver ships as a later configuration.
