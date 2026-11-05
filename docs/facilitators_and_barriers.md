# Facilitators and barriers (structured template)

> Synthetic data — for demonstration only. Items marked **[Simulation]** are supported by this
> repository's synthetic results; items marked **[Validate]** are hypotheses that **must be
> validated with real partners** before being relied on. Nothing here is a finding about any real system.

Use one row per point. Copy the table into partner discussions and fill in the last two columns.

## Technical

| # | Facilitator / barrier | Evidence | Status | Partner notes | Action |
|---|---|---|---|---|---|
| T1 | **F:** NEMSIS v3.5 already requires a UUID on each PatientCareReport, so no new identifier must be invented | NEMSIS XSD ([standards](standards_references.md)) | Verified (spec) | | |
| T2 | **F:** Exact joins on a carried UUID produced no false links | det_A/B/C precision 1.000 | [Simulation] | | |
| T3 | **B:** Each hand-off loses some UUIDs; losses compound across stages (A: 0.92×0.97×0.93 ≈ 0.83) | `results/pattern_logs.json` | [Simulation] | | |
| T4 | **B:** ED registration merge of the pre-admit is a key loss point in Pattern A | stage log | [Simulation] + [Validate] real merge rates | | |
| T5 | **B:** HIE match windows vs late PCR completion: 264 ED registrations had a candidate EMS message that arrived after the 12-h window | Pattern B log | [Simulation] + [Validate] real PCR completion delays | | |
| T6 | **B:** EHR may not keep a second visit-level identifier after merges/updates | Pattern C `identifier_retained` stage | [Validate] | | |
| T7 | **F:** Probabilistic linkage is a useful fallback; hybrid UUID+Splink recall 0.991 | `results/linkage_metrics.json` | [Simulation] | | |
| T8 | **B:** Interface engines may drop unknown Z-segments | general integration practice | [Validate] | | |

## Legal / governance

| # | Facilitator / barrier | Evidence | Status | Partner notes | Action |
|---|---|---|---|---|---|
| G1 | **F:** A non-identifying UUID lets the analytic join happen without exchanging names/DOB for matching | design | [Validate] with privacy counsel | | |
| G2 | **B:** Data-sharing agreements may not cover writing an EMS identifier into the hospital record | — | [Validate] | | |
| G3 | **B:** Who owns the identifier namespace (URI / assigning authority) and its documentation? | — | [Validate] | | |
| G4 | **F:** Existing HIE participation agreements may already cover ADT exchange (Pattern B) | — | [Validate] | | |

## Organizational

| # | Facilitator / barrier | Evidence | Status | Partner notes | Action |
|---|---|---|---|---|---|
| O1 | **F:** Shared QI interest — EMS wants outcome feedback (NEMSIS eOutcome section exists for this) | NEMSIS eOutcome elements | Verified (spec) / [Validate] interest | | |
| O2 | **B:** ED registration workload; merging pre-admits competes with throughput | — | [Validate] | | |
| O3 | **B:** Many small EMS agencies; onboarding each one is a fixed cost | — | [Validate] | | |

## Vendor

| # | Facilitator / barrier | Evidence | Status | Partner notes | Action |
|---|---|---|---|---|---|
| V1 | **F:** FHIR R4 `Encounter.identifier` is 0..* — an extra identifier is structurally allowed | FHIR R4 spec | Verified (spec) | | |
| V2 | **B:** EHR FHIR APIs may not permit third-party writes to Encounter | — | [Validate] | | |
| V3 | **B:** ePCR may not expose the UUID to outbound HL7/FHIR interfaces | — | [Validate] | | |
| V4 | **B:** Interface build and maintenance fees per connection | — | [Validate] | | |

## Workforce

| # | Facilitator / barrier | Evidence | Status | Partner notes | Action |
|---|---|---|---|---|---|
| W1 | **B:** Limited interface-analyst capacity at small/rural hospitals | — | [Validate] | | |
| W2 | **F:** Deterministic joins need far less analyst time than tuning/reviewing probabilistic matches | runtime + no clerical review in simulation | [Simulation] (runtime only) + [Validate] | | |
| W3 | **B:** Registrar training on finding/merging EMS pre-arrival records | — | [Validate] | | |

## Equity (cross-cutting)

| # | Facilitator / barrier | Evidence | Status | Partner notes | Action |
|---|---|---|---|---|---|
| E1 | **F:** UUID carry did not depend on demographics in the simulation, so recall was flat across groups | subgroup recall (det_C 0.905–0.987) | [Simulation] — by construction; [Validate] real carry parity (e.g. rural agencies may be connected later) | | |
| E2 | **B:** Probabilistic recall collapses for critically injured patients (Splink 0.31 vs UUID 0.92) because of aliases / unknown patients | `results/subgroup_recall.csv` | [Simulation] + [Validate] alias practices | | |
| E3 | **B:** Probabilistic recall gaps by race/ethnicity were small with precise arrival times but widened under date-only matching (Asian 0.79 vs White 0.89) | subgroup recall | [Simulation] | | |
