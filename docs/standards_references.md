# Standards references

> Synthetic data — for demonstration only. Independent portfolio project; not affiliated with,
> endorsed by, or produced for the CDC, NHTSA, NEMSIS, or any agency.

Every standards element this project names was checked against a public, official source.
**Access date for all sources below: 2026-11-05.** Where an element could not be verified, the
project describes the field generically ("simplified NEMSIS-inspired field") instead of citing an ID.

## NEMSIS v3.5.0

Source: NEMSIS v3.5.0 Data Dictionary element pages and XSDs on nemsis.org.

- Data dictionary index: <https://nemsis.org/technical-resources/version-3/version-3-data-dictionaries/>
- Element pages follow the pattern
  `https://nemsis.org/media/nemsis_v3/release-3.5.0/DataDictionary/PDFHTML/EMSDEMSTATE/sections/elements/<element>.xml`
- EMS dataset schema: <https://nemsis.org/media/nemsis_v3/release-3.5.0/XSDs/NEMSIS_XSDs/EMSDataSet_v3.xsd>
- Common types schema: <https://nemsis.org/media/nemsis_v3/release-3.5.0/XSDs/NEMSIS_XSDs/commonTypes_v3.xsd>

### The UUID

| Item | Verified content | Where used |
|---|---|---|
| `PatientCareReport` attribute `UUID` | `EMSDataSet_v3.xsd`: `<xs:attribute name="UUID" type="UUID" use="required"/>` on the `PatientCareReport` element | The identifier this project carries into the ED record (`ems_uuid`) |
| `UUID` simple type | `commonTypes_v3.xsd`: "A universally unique identifier used to track persistent objects over time."; pattern `[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[1-5][a-fA-F0-9]{3}-[89abAB][a-fA-F0-9]{3}-[a-fA-F0-9]{12}` | Generator emits UUID version 4; `tests/test_synth.py` checks the pattern |

### Data elements (names as published)

| Element | Name | Used for |
|---|---|---|
| eRecord.01 | Patient Care Report Number | `pcr_number` (agency-local; *not* used for linkage) |
| eResponse.01 | EMS Agency Number | `agency_id` (synthetic) |
| eTimes.03 | Unit Notified by Dispatch Date/Time | `unit_notified_ts`; start of the EMS→ED interval |
| eTimes.06 | Unit Arrived on Scene Date/Time | `arrived_scene_ts` |
| eTimes.07 | Arrived at Patient Date/Time | `arrived_patient_ts` |
| eTimes.09 | Unit Left Scene Date/Time | `left_scene_ts` |
| eTimes.11 | Patient Arrived at Destination Date/Time | `arrived_destination_ts`; Splink time comparison |
| eTimes.12 | Destination Patient Transfer of Care Date/Time | `transfer_of_care_ts`; HIE time tolerance |
| eScene.21 | Incident County | `incident_county` (county level only) |
| ePatient.02 / .03 | Last Name / First Name | demographic fields (with injected errors) |
| ePatient.07 | Patient's Home County | `patient_home_county` |
| ePatient.14 | Race | combined race list that **includes "Hispanic or Latino"** |
| ePatient.15 | Age | `patient_age` (estimated for unidentified patients) |
| ePatient.17 | Date of Birth | `patient_dob` |
| ePatient.25 | Sex | `patient_sex` (values Female / Male / Unknown). ePatient.13 *Gender* is marked DEPRECATED in v3.5.0 and is not used |
| eVitals.06 | SBP (Systolic Blood Pressure) | `sbp` |
| eVitals.10 | Heart Rate | `hr` |
| eVitals.14 | Respiratory Rate | `rr` |
| eVitals.23 | Total Glasgow Coma Score | `gcs` |
| eInjury.01 | Cause of Injury | ICD-10-CM external-cause code; pattern `([TV-Y][0-9]{2})((\.[0-9A-Z]{1,4})?)` checked in tests |
| eInjury.03 | Trauma Triage Criteria (High Risk for Serious Injury) | value labels copied verbatim (non-deprecated subset) |
| eInjury.04 | Trauma Triage Criteria (Moderate Risk for Serious Injury) | value labels copied verbatim (non-deprecated subset) |
| eHistory.17 | Alcohol/Drug Use Indicators | value labels copied verbatim, plus pertinent negative "None Reported" |
| eProcedures.03 | Procedure | NEMSIS uses SNOMED CT codes here; this project uses **simplified plain-text procedure labels** and does not reproduce SNOMED codes |
| eDisposition.27 | Unit Disposition | "Patient Contact Made" |
| eDisposition.30 | Transport Disposition | "Transport by This EMS Unit (This Crew Only)", "Patient Refused Transport", "No Transport" |
| eDisposition.01 / .02 | Destination/Transferred To, Name / Code | `destination_code` |
| eOutcome.01 | Emergency Department Disposition | discussed in docs as the ePCR-side home for ED outcome feedback |
| eOutcome.03 / .04 | External Report ID/Number Type / External Report ID/Number | discussed in docs: type list includes "Hospital-Receiving", a place for the hospital's encounter ID on the EMS side |
| eOutcome.10 | Emergency Department Diagnosis | discussed in docs |
| eOutcome.18 | Date/Time of Emergency Department Admission | discussed in docs |

## HL7 Version 2 (v2.5.1 messages)

Segment/field names were verified from the HL7 **v2-to-FHIR Implementation Guide** (continuous
build on build.fhir.org), whose segment maps list each v2 field with its name and data type, and
from the HL7 terminology server (terminology.hl7.org) for table values.

- v2-to-FHIR IG: <https://build.fhir.org/ig/HL7/v2-to-fhir/>
- PV1 → Encounter map: <https://build.fhir.org/ig/HL7/v2-to-fhir/ConceptMap-segment-pv1-to-encounter.html>
- PID → Patient map: <https://build.fhir.org/ig/HL7/v2-to-fhir/ConceptMap-segment-pid-to-patient.html>
- PV2 → Encounter map: <https://build.fhir.org/ig/HL7/v2-to-fhir/ConceptMap-segment-pv2-to-encounter.html>
- MSH → MessageHeader map: <https://build.fhir.org/ig/HL7/v2-to-fhir/ConceptMap-segment-msh-to-messageheader.html>
- DG1 → Condition map: <https://build.fhir.org/ig/HL7/v2-to-fhir/ConceptMap-segment-dg1-to-condition.html>
- Message maps index (ADT_A01, ADT_A05, …): <https://build.fhir.org/ig/HL7/v2-to-fhir/message_maps.html>

| Field | Name (data type) | Verified note |
|---|---|---|
| MSH-9 | Message Type (MSG) | maps to MessageHeader.eventCoding |
| MSH-10 | Message Control ID (ST) | |
| MSH-12 | Version ID (VID) | |
| PID-3 | Patient Identifier List (CX) | |
| PID-5 | Patient Name (XPN) | → Patient.name |
| PID-7 | Date/Time of Birth (DTM) | → Patient.birthDate |
| PID-8 | Administrative Sex (CWE) | → Patient.gender |
| PID-10 | Race (CWE) | IG: maps per local requirements (e.g. US Core Race extension) |
| PID-22 | Ethnic Group (CWE) | IG: local extension (e.g. US Core Ethnicity) |
| PV1-2 | Patient Class (CWE) | → Encounter.class |
| PV1-3 | Assigned Patient Location (PL) | |
| PV1-19 | Visit Number (CX) | → Encounter.identifier with type code `VN` |
| PV1-36 | Discharge Disposition (CWE) | → Encounter.hospitalization.dischargeDisposition (discussed; not populated) |
| PV1-37 | Discharged to Location (DLD) | → Encounter.hospitalization.destination; used by EMS for the destination facility |
| PV1-44 | Admit Date/Time (DTM) | → Encounter.period.start |
| PV1-45 | Discharge Date/Time (DTM) | → Encounter.period.end |
| **PV1-50** | **Alternate Visit ID (CX, repeating)** | mapped to an `Identifier` via CX[Identifier] — **where this project puts the EMS UUID** |
| PV2-38 | Mode of Arrival Code (CWE) | → Encounter extension `http://hl7.org/fhir/StructureDefinition/encounter-modeOfArrival` |
| DG1-3 | Diagnosis Code (CWE) | discussed; ED diagnoses are not sent in the simulated ADT messages |

HL7 v2 tables (terminology.hl7.org, HL7 Terminology code systems):

| Table | URL | Values used |
|---|---|---|
| 0001 Administrative Sex | <https://terminology.hl7.org/CodeSystem-v2-0001.html> | F, M, U |
| 0003 Event Type | <https://terminology.hl7.org/CodeSystem-v2-0003.html> | A01 Admit/visit notification; **A04 Register a patient**; **A05 Pre-admit a patient**; **A08 Update patient information** |
| 0004 Patient Class | <https://terminology.hl7.org/CodeSystem-v2-0004.html> | E Emergency |
| 0076 Message Type | <https://terminology.hl7.org/CodeSystem-v2-0076.html> | ADT |
| 0103 Processing ID | <https://terminology.hl7.org/CodeSystem-v2-0103.html> | T Training (all simulated messages) |
| 0104 Version ID | <https://terminology.hl7.org/CodeSystem-v2-0104.html> | 2.5.1 |
| 0203 Identifier Type | <https://terminology.hl7.org/CodeSystem-v2-0203.html> | MR Medical record number; PI Patient internal identifier; VN Visit number |
| 0354 Message Structure | <https://terminology.hl7.org/CodeSystem-v2-0354.html> | ADT_A01 (A01, A04, A08, A13); ADT_A05 (A05, A14, A28, A31) |
| 0430 Mode of Arrival Code | <https://terminology.hl7.org/CodeSystem-v2-0430.html> | A Ambulance; C Car; F On foot |

**Local conventions (not HL7-defined):** the assigning-authority namespace `EMSUUID` in PV1-50 /
PV1-19, the use of the PCR number as an EMS-side PID-3 value with type `PI`, and the alternative
`ZEM` Z-segment discussed in [architecture.md](architecture.md). Example messages additionally pass
**hl7apy** strict structure validation for v2.5.1 (`tests/test_patterns.py`).

## FHIR R4 (4.0.1)

- Encounter: <https://hl7.org/fhir/R4/encounter.html> — `identifier` 0..* Identifier; `status` 1..1;
  `class` 1..1 Coding; `period`; `hospitalization.dischargeDisposition`; `diagnosis`.
- Identifier datatype: <https://hl7.org/fhir/R4/datatypes.html#Identifier> — `use`
  (usual | official | temp | secondary | old), `type`, `system` ("The namespace for the identifier value"), `value`.
- Bundle: <https://hl7.org/fhir/R4/bundle.html> — `type` (document | message | transaction |
  transaction-response | batch | batch-response | history | searchset | collection); `entry.fullUrl`
  may be a `urn:uuid:`; `entry.request.method` (HTTP verb).
- Code systems (required bindings checked in code): Encounter status
  <https://hl7.org/fhir/R4/codesystem-encounter-status.html>, Administrative gender
  <https://hl7.org/fhir/R4/codesystem-administrative-gender.html>, HTTP verb
  <https://hl7.org/fhir/R4/codesystem-http-verb.html>, Bundle type
  <https://hl7.org/fhir/R4/codesystem-bundle-type.html>, Identifier use
  <https://hl7.org/fhir/R4/codesystem-identifier-use.html>.
- Extension `encounter-modeOfArrival` (R4, status draft, 0..1 Coding on Encounter):
  <https://hl7.org/fhir/R4/extension-encounter-modeofarrival.html>
- ICD-10-CM system URI `http://hl7.org/fhir/sid/icd-10-cm`: <https://hl7.org/fhir/R4/terminologies-systems.html>
- v3 ActCode `EMER` (emergency) for `Encounter.class`: <https://terminology.hl7.org/CodeSystem-v3-ActCode.html>
- Discharge disposition example code system (home, other-hcf, exp, oth, …):
  <https://terminology.hl7.org/CodeSystem-discharge-disposition.html>
- Condition clinical status: <https://terminology.hl7.org/CodeSystem-condition-clinical.html>

US Core (STU 6.1.0, built on FHIR 4.0.1):

- us-core-race extension: <https://hl7.org/fhir/us/core/STU6.1/StructureDefinition-us-core-race.html>
  — sub-extension `text` is 1..1; `ombCategory` 0..*. Bundles use the **text-only** form.
- us-core-ethnicity extension: <https://hl7.org/fhir/us/core/STU6.1/StructureDefinition-us-core-ethnicity.html>

Validation library: `fhir.resources` **6.1.0**, the last release whose default models are FHIR R4
4.0.1 (later releases default to R4B/R5). It enforces structure, cardinality, datatypes and unknown
elements; it does **not** enforce required-binding code values, so `patterns/pattern_c.py` checks
those explicitly (`REQUIRED_CODES`).

**Local conventions:** the identifier system URIs under `https://ems-ed-linkage-lab.example.org/…`
(`example.org` is reserved for documentation, RFC 2606). A real deployment would use a URI owned by
the state EMS office or HIE.

## ICD-10-CM

- CMS, *2026 ICD-10-CM* code descriptions in tabular order (file `icd10cm_codes_2026.txt`):
  <https://www.cms.gov/files/zip/2026-code-descriptions-tabular-order.zip>
  (landing page: <https://www.cms.gov/medicare/coding-billing/icd-10-codes>)

All 37 codes in `synth/codes.py` (4 MVC and 6 fall external-cause codes; 27 injury diagnosis codes)
were looked up in that file; descriptions are copied verbatim.

## Software

| Library | Version | Role |
|---|---|---|
| Splink | 5.0.0 | Fellegi–Sunter probabilistic linkage on DuckDB — <https://moj-analytical-services.github.io/splink/> |
| DuckDB | 2.0.0 | joins and analysis |
| python-hl7 | 0.4.5 | HL7 v2 parsing |
| hl7apy | 1.3.5 | strict v2.5.1 structure validation in tests |
| fhir.resources | 6.1.0 | FHIR R4 model validation |
