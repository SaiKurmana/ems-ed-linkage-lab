# Implementation guide (reusable template)

> Synthetic data — for demonstration only. This is a **template** drawn from a simulation, not
> guidance from any agency. Every step needs validation with real partners, their legal counsel and
> their vendors. Replace the `‹bracketed›` placeholders.

How to read this: think of the UUID as a **luggage tag**. The ePCR prints the tag; the integration
pattern decides whether the tag is tied to the bag (the ED record) at check-in (Pattern A or C) or
reattached later by a sorting hub that matches bags by description (Pattern B). Most of the work is
not the tag — it is agreeing who ties it on, where it goes, and how you check it stayed on.

## 0. Common prerequisites (all patterns)

| Item | Detail | Owner |
|---|---|---|
| Use case & scope | e.g. "link EMS transports for MVC and fall injuries to ED encounters at ‹N› hospitals for injury surveillance and EMS QI" | State EMS office + health department |
| Identifier convention | UUID = NEMSIS `PatientCareReport/@UUID`; HL7 v2 location (PV1-50, assigning authority `‹EMSUUID›`, type `VN`); FHIR `Identifier.system` URI `‹https://…/ems-pcr-uuid›` owned by `‹state EMS office or HIE›` | Governance group |
| Legal basis & agreements | data-use / data-sharing agreements, BAAs where required, HIE participation agreements; documented minimum-necessary data set | Legal / privacy officers of each party |
| ePCR capability | confirm the ePCR exposes the UUID to outbound interfaces (not only in the NEMSIS export) | ePCR vendor |
| EHR capability | confirm the ED encounter can store a second visit-level identifier and that it survives merges, transfers and updates | Hospital EHR team |
| Testing data | synthetic or de-identified test patients only; this repository's `examples/` can seed test cases | Everyone |
| Success metrics | UUID carry rate, message/API error rate, latency, false-link audits, subgroup carry parity | Governance group |

## Pattern A — point-to-point HL7 v2

**Who must be involved:** EMS agency operations lead; ePCR vendor interface team; hospital
interface/integration team; ED registration leadership; hospital privacy officer; state EMS data manager.

**Technical steps**
1. Write an interface specification: ADT^A05 (or the hospital's preferred pre-arrival event), segments
   MSH/EVN/PID/PV1/PV2, PV1-50 = `‹uuid›^^^‹EMSUUID›^VN`, PV2-38 = `A`.
2. Establish transport (VPN/MLLP or the hospital's standard) and ACK handling; define retry/queue rules.
3. Configure the interface engine to route the pre-admit to ED registration and to **preserve PV1-50**.
4. Define the registration workflow: how the registrar finds and merges the pre-admit (tracking-board
   cue, unit number, arrival time). This is the most failure-prone step in the simulation.
5. Ensure the hospital's own outbound ADT (A04/A08) carries PV1-50 to downstream consumers.

**Testing:** unit tests on message build/parse (see `tests/test_patterns.py`); end-to-end tests with
synthetic patients including unknown/alias patients, merges, and transfers; measure carry rate.

**Go-live:** phased by agency–hospital pair; daily reconciliation report (EMS transports vs ED
encounters with PV1-50) for the first ‹30› days; escalation contacts.

## Pattern B — HIE intermediary

**Who must be involved:** HIE technical and governance staff; ePCR vendor; hospital interface team;
state EMS office; health department (if it is the analytic user).

**Technical steps**
1. Onboard EMS agencies as HIE data senders (ADT^A04 per PCR, UUID in PV1-19 with assigning authority
   `‹EMSUUID›`, PV1-37 destination, PV1-45 transfer of care).
2. Configure the HIE matcher: destination facility, time tolerance, **match window long enough for
   real PCR completion delays**, demographic rules, tie handling, and a manual-review queue.
3. Define the write-back: ADT^A08 to the hospital with PV1-50, or HIE-side storage queried by analysts.
4. Monitor late messages and unmatched queues; tune the window (the simulation shows the trade-off).

**Testing:** replay synthetic message streams with realistic delays; audit a sample of matches for
false links; report match rate by facility and by patient group.

**Go-live:** start with read-only matching (no write-back) to measure match quality, then enable
write-back.

## Pattern C — FHIR R4 API

**Who must be involved:** ePCR vendor (integration service owner); hospital EHR/FHIR platform team;
hospital security (OAuth client registration, scopes); privacy officer.

**Technical steps**
1. Register the integration service as a FHIR client with least-privilege scopes (read/write
   Encounter for the ED context only).
2. Define how the service locates the ED Encounter (search parameters agreed with the hospital).
3. Write the identifier: `Encounter.identifier` with `use = secondary`, `system = ‹URI›`, `value = ‹uuid›`
   via a transaction Bundle (PUT) or PATCH, per the EHR's API support.
4. Validate payloads (FHIR R4 profile/validator); handle 4xx/5xx with retries and alerting.
5. Confirm the identifier persists across later EHR updates and appears in bulk/downstream exports.

**Testing:** contract tests against the hospital's sandbox; validation of every bundle (as in
`patterns/pattern_c.py`); persistence tests after encounter updates/merges.

**Go-live:** feature flag per agency–hospital pair; dashboards for call success and identifier retention.

## After go-live (all patterns)

- Monthly reconciliation: transports with vs without a carried UUID, by agency, hospital and patient group.
- Periodic audit for wrong-UUID links (especially Pattern B).
- Keep a probabilistic fallback for records the UUID misses (the simulation's hybrid had the best recall).
- Review the minimum-necessary data set annually ([privacy_and_security.md](privacy_and_security.md)).
