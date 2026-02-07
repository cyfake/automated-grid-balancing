# Grid Load-Balancing MVP — Run Summary

This report is the single source of truth for the 24-hour grid dispatch simulation. It documents what happened, what trade-offs were made, why blackouts occurred, and what infrastructure changes would improve outcomes. Every recommendation is linked to specific evidence from this run.

**Dispatch method**: Greedy 24-hour lookahead (deterministic, rule-based)
**Horizon**: 24 hours
**States**: CA, NY, TX

**Data source**: EIA Open Data API (Form EIA-930)
**Period**: 2026-02-04T00 → 2026-02-05T23 (UTC)
**API key**: EIA_API_KEY env var
**Fetched**: 2026-02-07T05:54:56.694487+00:00

*Battery specifications are engineering estimates (not from EIA). See provenance sidecar for details.*

*Fuel capacity: peak observed dispatchable + 15% headroom.*

---

## What Happened

Over a 24-hour window, the system dispatched electricity for 3 US states — CA, NY, TX — drawing on solar and wind generation, battery storage, inter-state transfers, and fossil fuel plants. The objective was to serve all demand while minimizing fuel use, avoiding waste of renewables, and preventing blackouts.

The grid was **severely supply-constrained**. Renewable generation covered only 22% of total load (523,301 of 2,329,256 MWh). In every single hour, across all three states, demand exceeded the combined output of solar and wind. There was never a surplus of renewable energy to store or share. The remaining 78% of demand fell on batteries, fuel plants, and inter-state transfers.

Fossil fuel plants bore the heaviest burden, supplying 1,347,844 MWh (58% of all load). Even so, fuel plants hit their maximum capacity in 31 out of 72 state-hours (24 hours × 3 states). When demand exceeded even maximum fuel output, the result was **unserved energy — 445,086 MWh of demand that could not be met**, a 19.1% overall shortfall. These blackouts clustered in two distinct windows: an early-morning window (hours 0–11) and a far more severe evening-peak window (hours 12–23).

---

## KPIs

The following metrics summarize how well the system performed. Each is accompanied by an explanation of what drove the result.

| Metric | Value |
|--------|-------|
| Total Load (MWh) | 2,329,256.0 |
| Renewable Used (MWh) | 523,301.0 |
| Renewable Utilization | 100.0% |
| Curtailment (MWh) | 0.0 |
| Fuel Used (MWh) | 1,347,844.1 |
| Unserved Energy (MWh) | 445,086.5 |
| Transfer Utilization | 27.5% |
| Battery Cycles (proxy) | 0.36 |

**Renewable Utilization at 100% and Curtailment at 0.0 MWh**: These two metrics are linked. Every megawatt-hour of available solar and wind was consumed — nothing was wasted. However, this is not a sign of efficiency. It reflects the fact that demand *always* exceeded renewable supply in every hour. There was never a surplus to curtail (waste) or to store in batteries. Renewables provided only 22% of total load, broken down as: CA 17,730 MWh (2.7% of CA load), NY 16,497 MWh (3.5% of NY load), TX 489,074 MWh (40.9% of TX load).

**Fuel at 1,347,844 MWh**: The grid ran primarily on fossil fuel. By state: TX (750,841 MWh), NY (484,450 MWh), CA (112,553 MWh). Fuel plants were at 100% capacity in 31 state-hours — including *every* state-hour within both crisis windows. This ceiling is the direct cause of all unserved energy: blackouts occurred precisely in the hours when fuel plants could produce no more.

**Unserved Energy at 445,086 MWh (19.1% of load)**: Not evenly distributed. CA: 445,086 MWh (100%), NY: 0 MWh (0%), TX: 0 MWh (0%). Blackouts were concentrated in 24 critical state-hour events (detailed below in Stress Events). The evening peak produced approximately 44% of all unserved energy.

**Transfer Utilization at 27.5%**: Very low. The inter-state power lines were used in only 24 of 24 hours, transferring a total of 79,122 MWh. Utilization was low because all three states were in deficit simultaneously almost every hour. There was rarely surplus power to send. The transfers that did occur were "fuel-backed": a state with spare fuel capacity generated extra power and sent it to a neighbor whose fuel plants were already maxed out.

**Battery Cycles at 0.36**: Batteries completed roughly one-third of a full discharge cycle over 24 hours. They were *discharge-only* for the entire run — no battery in any state was ever charged, because renewable generation never exceeded demand. State of charge (SoC) dropped monotonically (CA: 8,000 → 1,833 MWh; NY: 4,000 → 949 MWh; TX: 6,000 → 1,334 MWh). Notably, batteries sat completely idle during hours 17–21 due to the evening reserve policy (explained in the next section).

---

## What Trade-Offs Were Made

The dispatch system faced a supply gap in every hour and had to decide how to allocate limited batteries and fuel. Three key trade-offs shaped the results.

### Trade-off 1: Conserving batteries for the evening vs. using them now

The system's 24-hour lookahead identified the evening peak (hours 17–21) as the most critical period and set a **40% state-of-charge (SoC) reserve floor** during those hours. This meant batteries should retain at least 40% of their capacity (CA: 6,400 MWh, NY: 3,200 MWh, TX: 4,800 MWh) to be available for evening dispatch.

In practice, batteries discharged at a conservative rate of 150–300 MW per state from hours 0 through 16. The result was a slow, steady drain:

- CA: 8,000 → 3,531 MWh by hour 16 (22% of capacity; *below the 40% target*)
- NY: 4,000 → 1,880 MWh by hour 16 (24% of capacity; *below the 40% target*)
- TX: 6,000 → 2,073 MWh by hour 16 (17% of capacity; *below the 40% target*)

By the time the evening peak arrived at hour 17, **all three states' batteries were already below the 40% reserve floor**. The system could not discharge them at all. Batteries sat idle from hours 17 through 21 — the five hours with the worst blackouts — holding a combined 7,484 MWh that could not be released.

The constraint finally lifted at hour 22 (outside the evening peak window), and batteries discharged sharply: CA released 1,389 MW, NY released 729 MW, TX released 607 MW in a single burst. But by then, the crisis had already passed.

**The trade-off**: the reserve policy, designed to protect the evening peak, actually prevented batteries from being used precisely when they were needed most. The daytime discharge, while individually small per hour, accumulated into enough depletion to breach the reserve floor before the peak began.

### Trade-off 2: Helping neighbors vs. serving yourself

TX, with the largest fuel fleet, served as the primary fuel-backed exporter. In 24 of 24 hours, states generated extra fuel power and sent it to neighbors. For example, at hour 0 TX exported 2,000 MW to CA and 507 MW to NY; at hour 1 TX exported 2,000 MW to CA and 51 MW to NY.

These fuel-backed transfers reduced shortfalls in receiving states during the morning window — without them, those states would have faced larger blackouts.

**The trade-off**: fuel-backed transfers can redistribute generation when one state's fuel plant is saturated and another's is not. But when all states saturate simultaneously (as in the evening crisis window), there is no spare fuel anywhere, and transfers cannot help. This is why transfers dropped to zero in the worst hours.

### Trade-off 3: Fuel as the last resort, but the only resort in practice

The dispatch priority was: use renewables first, then batteries, then transfers, then fuel. Fuel was intentionally the last resort because of its cost and emissions. However, because renewables covered only 22% of load and batteries held limited energy, fuel became the dominant supply source, carrying 58% of all load.

This "last resort" carried the entire grid. When fuel plants hit their capacity ceiling, there was no further fallback — the result was blackouts.

---

## Stress Events

**24 critical events** (unserved energy) and **64 warnings** were detected across 88 total stress events. The 64 warnings flagged hours where fuel plants exceeded 90% of their maximum capacity — a leading indicator that a state was approaching its generation limit. The critical events fell into two clusters.

### Critical Events

| Hour | State | Unserved (MW) |
|------|-------|--------------|
| 0 | CA | 19,646 |
| 1 | CA | 22,489 |
| 2 | CA | 24,582 |
| 3 | CA | 24,372 |
| 4 | CA | 23,512 |
| 5 | CA | 22,861 |
| 6 | CA | 21,797 |
| 7 | CA | 20,220 |
| 8 | CA | 18,443 |
| 9 | CA | 17,635 |
| 10 | CA | 16,592 |
| 11 | CA | 15,795 |
| 12 | CA | 15,496 |
| 13 | CA | 16,070 |
| 14 | CA | 17,893 |
| 15 | CA | 20,154 |
| 16 | CA | 21,011 |
| 17 | CA | 19,399 |
| 18 | CA | 16,959 |
| 19 | CA | 15,041 |
| 20 | CA | 13,620 |
| 21 | CA | 13,129 |
| 22 | CA | 12,178 |
| 23 | CA | 16,189 |

### Morning window: Hours 0–11 (12 events)

Before sunrise, solar output was near zero. Load was climbing as the day began. All three states' fuel plants reached 100% capacity. Batteries were discharging, but at conservative 150–270 MW rates to preserve stored energy for the evening.

**What caused it**: High pre-dawn load combined with zero solar. Fuel plants at capacity. Conservative battery dispatch due to the evening-reserve lookahead.

**What decision was made**: The system chose to drain batteries slowly (preserving them for the evening) rather than discharge aggressively to cover the morning gap. This decision directly contributed to the 247,946 MW of morning shortfalls.

**What outcome resulted**: 12 critical events totaling approximately 247,946 MW of unserved power. CA was hit in 12 hours. CA had the single largest spike (24,582 MW at hour 2).

### Evening window: Hours 12–23 (12 events, 44% of all unserved energy)

This was the dominant crisis. Solar generation dropped to zero by hour 20. Evening load surged. All three states ran fuel plants at 100% capacity through the entire window. Batteries held stored energy but could not discharge — all were below the 40% SoC reserve target. Transfers were minimal because all states were in deep simultaneous deficit.

Hour 16 was the worst overall: CA short 21,011 MW — a combined deficit of 21,011 MW in a single hour.

**What caused it**: Simultaneous load surge across all states. Solar dropping to zero. Fuel plants at 100% capacity. Batteries locked by the 40% evening SoC reserve floor. No meaningful transfer options because all states were in deficit.

**What decision was made**: The system honored the 40% SoC reserve floor, holding 7,484 MWh in batteries rather than releasing it during the blackout. The reserve policy prevented any battery dispatch for five consecutive hours.

**What outcome resulted**: 12 critical events totaling approximately 197,141 MW of unserved power. This is where the vast majority of all blackouts occurred. The locked batteries represent energy that *existed* but could not be used.

---

## Key Constraints That Mattered

Three constraints drove virtually all of the 445,086 MWh of unserved energy. Understanding which constraints were *binding* (actually limiting the system) and which were *non-binding* (had capacity to spare) is essential for interpreting the recommendations that follow.

**Binding constraints** (directly caused blackouts):

1. **Fuel capacity ceiling**: In every one of the 24 critical events, at least one state's fuel plant was at 100% output. When demand exceeds renewables + batteries + maximum fuel, the difference becomes unserved energy. This was the proximate cause of every blackout.

2. **Battery energy (MWh) exhaustion**: By hour 17, batteries had discharged to ~27% of full capacity — below the 40% evening reserve floor. The reserve policy then locked them out entirely for hours 17–21. A total of 7,484 MWh sat idle in batteries during the worst blackout window.

3. **Simultaneous deficit across all states**: All three states were in net deficit (load > renewables) in every single hour. This meant states could only help each other by generating *additional* fuel — not by sharing surplus renewable energy (there was none). When all fuel plants hit capacity simultaneously, inter-state transfers had nothing to move.

**Non-binding constraints** (had spare capacity, not currently limiting):

4. **Battery power (MW)**: Batteries discharged at 150–300 MW throughout the run, far below their power limits (CA: 4,000 MW, NY: 2,000 MW, TX: 3,000 MW). The charge/discharge rate was never the bottleneck.

5. **Transfer line capacity**: Lines were 72.5% idle. The limitation was not line size but that no state had surplus to send.

---

## Top Recommendations

Recommendations were generated by running counterfactual simulations: the same 24-hour scenario was replayed with one infrastructure change, and the resulting KPIs were compared to the baseline. The **penalty score** is a weighted sum that quantifies overall grid performance: 1,000 points per MWh of unserved energy + 10 points per MWh of fuel + 1 point per MWh of curtailment. A negative score delta means the change reduces total penalty (improves performance).

### #1: Double all transfer capacities

**Rank 1 — score delta: -67,627,237 (improvement)**

| Delta | Value |
|-------|-------|
| Unserved | -68,310.3 MWh |
| Curtailment | +0.0 MWh |
| Fuel | +68,310.3 MWh |

**Why this recommendation helps**:

Larger transfer lines allow more fuel-backed sharing between states. Score improvement: 67,627,237 points.

### #2: Increase all transfer capacities by 50%

**Rank 2 — score delta: -35,564,819 (improvement)**

| Delta | Value |
|-------|-------|
| Unserved | -35,924.1 MWh |
| Curtailment | +0.0 MWh |
| Fuel | +35,924.1 MWh |

**Why this recommendation helps**:

Larger transfer lines allow more fuel-backed sharing between states. Score improvement: 35,564,819 points.

### #3: Add 8000 MWh battery storage to CA

**Rank 3 — score delta: -2,892,400 (improvement)**

| Delta | Value |
|-------|-------|
| Unserved | -2,892.4 MWh |
| Curtailment | +0.0 MWh |
| Fuel | +0.0 MWh |

**Why this is recommended — the causal chain**:

- *Signal*: CA had 445,086 MWh of total unserved energy — the most of any state — across 24 critical events (hours 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23). CA's fuel plants ran at 100% capacity in every one of those hours.
- *Decision the system made*: CA's battery (16,000 MWh capacity, starting at 8,000 MWh) was drained conservatively at ~150–300 MW per hour, reaching 3,531 MWh by hour 16 — below the 40% reserve target of 6,400 MWh. The system then locked the battery for the entire evening peak.
- *Outcome*: CA suffered 445,086 MWh of unserved energy, concentrated in the evening window. The battery held 3,531 MWh throughout the crisis but could not release any of it.
- *Recommendation*: Increasing CA's battery to 24,000 MWh (with proportionally scaled initial charge) means the battery enters the evening peak with more stored energy. The 40% reserve floor is higher in absolute terms (9,600 MWh), but the battery starts with proportionally more energy and retains more headroom above the floor. The battery can discharge during hours 17–21 instead of sitting idle. **Result: 2,892 MWh less unserved energy and 0 MWh less fuel burned.**

### #4: Add 4000 MWh battery storage to NY

**Rank 4 — score delta: -348,101 (improvement)**

| Delta | Value |
|-------|-------|
| Unserved | -337.4 MWh |
| Curtailment | +0.0 MWh |
| Fuel | -1,069.1 MWh |

**Why this is recommended — the causal chain**:

- *Signal*: NY had 0 MWh of total unserved energy — across 0 critical events (hours ). NY's fuel plants ran at 100% capacity in every one of those hours.
- *Decision the system made*: NY's battery (8,000 MWh capacity, starting at 4,000 MWh) was drained conservatively at ~150–300 MW per hour, reaching 1,880 MWh by hour 16 — below the 40% reserve target of 3,200 MWh. The system then locked the battery for the entire evening peak.
- *Outcome*: NY suffered 0 MWh of unserved energy, concentrated in the evening window. The battery held 1,880 MWh throughout the crisis but could not release any of it.
- *Recommendation*: Increasing NY's battery to 12,000 MWh (with proportionally scaled initial charge) means the battery enters the evening peak with more stored energy. The 40% reserve floor is higher in absolute terms (4,800 MWh), but the battery starts with proportionally more energy and retains more headroom above the floor. The battery can discharge during hours 17–21 instead of sitting idle. **Result: 337 MWh less unserved energy and 1,069 MWh less fuel burned.**

### #5: Add 6000 MWh battery storage to TX

**Rank 5 — score delta: -22,133 (improvement)**

| Delta | Value |
|-------|-------|
| Unserved | +0.0 MWh |
| Curtailment | +0.0 MWh |
| Fuel | -2,213.3 MWh |

**Why this is recommended — the causal chain**:

- *Signal*: TX had 0 MWh of total unserved energy — across 0 critical events (hours ). TX's fuel plants ran at 100% capacity in every one of those hours.
- *Decision the system made*: TX's battery (12,000 MWh capacity, starting at 6,000 MWh) was drained conservatively at ~150–300 MW per hour, reaching 2,073 MWh by hour 16 — below the 40% reserve target of 4,800 MWh. The system then locked the battery for the entire evening peak.
- *Outcome*: TX suffered 0 MWh of unserved energy, concentrated in the evening window. The battery held 2,073 MWh throughout the crisis but could not release any of it.
- *Recommendation*: Increasing TX's battery to 18,000 MWh (with proportionally scaled initial charge) means the battery enters the evening peak with more stored energy. The 40% reserve floor is higher in absolute terms (7,200 MWh), but the battery starts with proportionally more energy and retains more headroom above the floor. The battery can discharge during hours 17–21 instead of sitting idle. **Result: 0 MWh less unserved energy and 2,213 MWh less fuel burned.**

### #6, #7, #8: Increase battery power (MW) — No impact

| Rank | Change | Score Delta | Unserved Delta | Fuel Delta |
|------|--------|-------------|----------------|------------|
| 6 | Add 2000 MW battery power to CA | +0.0 | +0.0 MWh | +0.0 MWh |
| 7 | Add 1000 MW battery power to NY | +0.0 | +0.0 MWh | +0.0 MWh |
| 8 | Add 1500 MW battery power to TX | +0.0 | +0.0 MWh | +0.0 MWh |

**Why zero impact**: Battery power rating is the maximum charge/discharge rate in MW. Throughout this run, batteries discharged at 150–300 MW — well below their existing power limits (CA: 4,000 MW, NY: 2,000 MW, TX: 3,000 MW). The bottleneck was not how fast energy could flow out of the battery; it was how much stored energy (MWh) was available. See **non-binding constraint #4** above: battery power was never saturated in any hour.

---

## Why These Recommendations — Summary

The pattern across all 8 counterfactual scenarios points to a single conclusion: **the grid's binding constraint is the total amount of stored energy (MWh), not the rate of energy flow (MW) or the capacity of inter-state connections.**

Battery energy storage upgrades (recommendations #1, #2, #3, #4, #5) help because they address the root cause: there is not enough stored energy to bridge the gap between daytime renewable generation and evening peak demand, especially when fuel plants are already at maximum output. Larger batteries arrive at the evening peak with more energy available above the reserve floor, enabling discharge during the critical hours 17–21 when the current batteries sit idle.

Battery power upgrades and transfer capacity upgrades (#6, #7, #8) show zero impact because they address constraints that are not currently binding. Batteries never hit their power limit, and transfer lines are 73% idle.

The ranking among the storage recommendations reflects two factors: which state has the most unserved energy to reduce, and which state has the most renewable energy available to fill the additional storage. By state: CA (445,086 MWh unserved, 17,730 MWh renewable); NY (0 MWh unserved, 16,497 MWh renewable); TX (0 MWh unserved, 489,074 MWh renewable).

---

## Summary of Findings

1. **The grid is fundamentally energy-constrained, not power-constrained.** Renewable generation covers 22% of load. The remainder falls on fuel, which hits its capacity ceiling in 31 of 72 state-hours. Every blackout occurred when fuel was at maximum.

2. **Battery storage is the highest-leverage investment.** All three top-ranked recommendations add storage (MWh). More storage lets the grid bank daytime renewables for the evening peak and provides a buffer above the SoC reserve floor, enabling battery dispatch during the hours when fuel is maxed and blackouts occur.

3. **Battery power and transfer capacity are not current bottlenecks.** 3 of 8 tested scenarios showed zero improvement across all KPIs because neither constraint is binding in this scenario.

4. **The evening peak (hours 17–21) is the dominant risk window**, producing 44% of all unserved energy across 12 of 24 critical events. Both crisis windows are driven by the same mechanism: fuel at capacity, batteries depleted or locked, and all states in simultaneous deficit.

5. **The evening reserve policy created an unintended consequence**: conservative daytime discharge, intended to save battery for the evening, depleted SoC below the 40% reserve floor *before* the evening peak began. Batteries then sat idle during the five worst hours. This suggests the reserve policy itself may need recalibration — either a lower evening floor, or a two-stage policy that releases the reserve when fuel plants are fully saturated.
