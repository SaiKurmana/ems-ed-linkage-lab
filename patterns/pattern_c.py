"""Pattern C — FHIR R4 API (vendor / integration-service style).

Flow (simulated):
  1. At transfer of care, the ePCR vendor's integration service locates the ED Encounter on the
     hospital's FHIR API and sends a `transaction` Bundle that PUTs the Encounter with an
     ADDITIONAL Encounter.identifier: {system: <EMS UUID system URI>, value: <UUID>, use: secondary}.
  2. The hospital's ED record (exported here as a `collection` Bundle: Patient, Encounter,
     Condition) keeps that identifier alongside its own visit-number identifier.

Every Bundle is validated with fhir.resources (FHIR R4 4.0.1 models). The ED record's UUID is
read back from the validated Encounter.identifier whose system equals the EMS UUID system.

Failure stages (configurable): api_enabled -> api_call_success -> identifier_retained.
"""

from __future__ import annotations

import uuid

import numpy as np
import pandas as pd
from fhir.resources.bundle import Bundle

from common import EMS_UUID_SYSTEM, HOSPITAL_MRN_SYSTEM_TMPL, HOSPITAL_VISIT_SYSTEM_TMPL
from patterns.common import expected_carry_rate, stage
from synth.codes import ALL_ICD10CM, dotted

STAGES = ["api_enabled", "api_call_success", "identifier_retained"]
V2_0203 = "http://terminology.hl7.org/CodeSystem/v2-0203"
V2_0430 = "http://terminology.hl7.org/CodeSystem/v2-0430"
ACT_CODE = "http://terminology.hl7.org/CodeSystem/v3-ActCode"
DISCH = "http://terminology.hl7.org/CodeSystem/discharge-disposition"
ICD10CM = "http://hl7.org/fhir/sid/icd-10-cm"
MODE_OF_ARRIVAL_EXT = "http://hl7.org/fhir/StructureDefinition/encounter-modeOfArrival"
US_CORE_RACE = "http://hl7.org/fhir/us/core/StructureDefinition/us-core-race"
US_CORE_ETH = "http://hl7.org/fhir/us/core/StructureDefinition/us-core-ethnicity"
ARRIVAL_TEXT = {"A": "Ambulance", "C": "Car", "F": "On foot"}
GENDER = {"F": "female", "M": "male", "U": "unknown"}
# Simplified ED disposition -> R4 example value set discharge-disposition (+ text)
DISPOSITION = {
    "discharged": ("home", "Home", "Discharged home"),
    "admitted": ("oth", "Other", "Admitted as inpatient to this hospital"),
    "transferred": ("other-hcf", "Other healthcare facility", "Transferred to another hospital"),
    "died": ("exp", "Expired", "Died in the emergency department"),
}


def _uid(ns: str, key: str) -> str:
    """Deterministic resource ids (uuid5) so exports are byte-stable across runs."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{ns}/{key}"))


def _iso(ts) -> str:
    return pd.Timestamp(ts).strftime("%Y-%m-%dT%H:%M:%S") + "-05:00"


def encounter_resource(
    r, ems_uuid: str | None, patient_ref: str, condition_refs: list[str] | None = None
) -> dict:
    ident = [
        {
            "use": "usual",
            "type": {"coding": [{"system": V2_0203, "code": "VN", "display": "Visit number"}]},
            "system": HOSPITAL_VISIT_SYSTEM_TMPL.format(hospital=r.hospital_id),
            "value": r.ed_encounter_id,
        }
    ]
    if ems_uuid:
        ident.append(
            {
                "use": "secondary",
                "type": {"text": "EMS patient care report UUID"},
                "system": EMS_UUID_SYSTEM,
                "value": ems_uuid,
            }
        )
    enc = {
        "resourceType": "Encounter",
        "id": _uid("Encounter", r.ed_encounter_id),
        "extension": [
            {
                "url": MODE_OF_ARRIVAL_EXT,
                "valueCoding": {
                    "system": V2_0430,
                    "code": r.arrival_mode,
                    "display": ARRIVAL_TEXT.get(r.arrival_mode, ""),
                },
            }
        ],
        "identifier": ident,
        "status": "finished",
        "class": {"system": ACT_CODE, "code": "EMER", "display": "emergency"},
        "subject": {"reference": patient_ref},
        "period": {"start": _iso(r.arrival_ts)},
        "serviceProvider": {"display": f"Hospital {r.hospital_id} (synthetic)"},
    }
    if isinstance(r.disposition, str):
        code, display, text = DISPOSITION[r.disposition]
        enc["hospitalization"] = {
            "dischargeDisposition": {
                "coding": [{"system": DISCH, "code": code, "display": display}],
                "text": text,
            }
        }
    if condition_refs:
        enc["diagnosis"] = [
            {"condition": {"reference": c}, "rank": i + 1} for i, c in enumerate(condition_refs)
        ]
    return enc


def patient_resource(r) -> dict:
    p = {
        "resourceType": "Patient",
        "id": _uid("Patient", r.mrn),
        "identifier": [
            {
                "use": "usual",
                "type": {
                    "coding": [
                        {"system": V2_0203, "code": "MR", "display": "Medical record number"}
                    ]
                },
                "system": HOSPITAL_MRN_SYSTEM_TMPL.format(hospital=r.hospital_id),
                "value": r.mrn,
            }
        ],
        "name": [{"family": r.last_name.title(), "given": [r.first_name.title()]}],
        "gender": GENDER.get(r.sex, "unknown"),
        # US Core race/ethnicity extensions, text-only form (ombCategory codes omitted)
        "extension": [
            {"url": US_CORE_RACE, "extension": [{"url": "text", "valueString": r.race}]},
            {"url": US_CORE_ETH, "extension": [{"url": "text", "valueString": r.ethnicity}]},
        ],
    }
    if isinstance(r.dob, str) and r.dob:
        p["birthDate"] = r.dob
    return p


def condition_resources(r, patient_ref: str, encounter_ref: str) -> list[dict]:
    out = []
    for code in [c for c in str(r.dx_codes).split("|") if c] + [r.external_cause_code]:
        out.append(
            {
                "resourceType": "Condition",
                "id": _uid("Condition", f"{r.ed_encounter_id}/{code}"),
                "clinicalStatus": {
                    "coding": [
                        {
                            "system": "http://terminology.hl7.org/CodeSystem/condition-clinical",
                            "code": "active",
                        }
                    ]
                },
                "code": {
                    "coding": [
                        {"system": ICD10CM, "code": dotted(code), "display": ALL_ICD10CM[code]}
                    ]
                },
                "subject": {"reference": patient_ref},
                "encounter": {"reference": encounter_ref},
            }
        )
    return out


def transaction_bundle(r, ems_uuid: str) -> dict:
    """What the integration service sends: PUT the ED Encounter with the extra identifier."""
    enc = encounter_resource(r, ems_uuid, f"Patient/{_uid('Patient', r.mrn)}")
    enc["status"] = "in-progress"
    enc.pop("hospitalization", None)
    return {
        "resourceType": "Bundle",
        "id": _uid("txn", r.ed_encounter_id),
        "type": "transaction",
        "timestamp": _iso(r.arrival_ts),
        "entry": [
            {
                "fullUrl": f"https://ehr-{r.hospital_id.lower()}.example.org/fhir/Encounter/{enc['id']}",
                "resource": enc,
                "request": {"method": "PUT", "url": f"Encounter/{enc['id']}"},
            }
        ],
    }


def ed_record_bundle(r, ems_uuid: str | None) -> dict:
    """The hospital's ED record for one encounter, as a FHIR R4 `collection` Bundle."""
    pat = patient_resource(r)
    pref = f"urn:uuid:{pat['id']}"
    enc_id = _uid("Encounter", r.ed_encounter_id)
    eref = f"urn:uuid:{enc_id}"
    conds = condition_resources(r, pref, eref)
    enc = encounter_resource(r, ems_uuid, pref, [f"urn:uuid:{c['id']}" for c in conds])
    entries = [pat, enc, *conds]
    return {
        "resourceType": "Bundle",
        "id": _uid("ed-record", r.ed_encounter_id),
        "type": "collection",
        "timestamp": _iso(r.arrival_ts),
        "entry": [{"fullUrl": f"urn:uuid:{x['id']}", "resource": x} for x in entries],
    }


# FHIR R4 required-binding code systems used in our bundles (verified from hl7.org/fhir/R4).
# fhir.resources 6.1.0 enforces structure, cardinality, datatypes and unknown elements, but not
# required-binding code values, so those are checked explicitly here.
REQUIRED_CODES = {
    "Bundle.type": {
        "document",
        "message",
        "transaction",
        "transaction-response",
        "batch",
        "batch-response",
        "history",
        "searchset",
        "collection",
    },
    "Bundle.entry.request.method": {"GET", "HEAD", "POST", "PUT", "DELETE", "PATCH"},
    "Encounter.status": {
        "planned",
        "arrived",
        "triaged",
        "in-progress",
        "onleave",
        "finished",
        "cancelled",
        "entered-in-error",
        "unknown",
    },
    "Identifier.use": {"usual", "official", "temp", "secondary", "old"},
    "Patient.gender": {"male", "female", "other", "unknown"},
}


class FHIRCodeError(ValueError):
    pass


def _check(path: str, value) -> None:
    if value is not None and value not in REQUIRED_CODES[path]:
        raise FHIRCodeError(f"{path}: {value!r} is not in the required R4 value set")


def validate(bundle: dict) -> Bundle:
    """Validate with fhir.resources (R4 4.0.1 models) + required-binding code checks.

    Raises pydantic.ValidationError (structure) or FHIRCodeError (code value).
    """
    b = Bundle.parse_obj(bundle)
    _check("Bundle.type", b.type)
    for entry in b.entry or []:
        if entry.request is not None:
            _check("Bundle.entry.request.method", entry.request.method)
        res = entry.resource
        if res.resource_type == "Encounter":
            _check("Encounter.status", res.status)
        if res.resource_type == "Patient":
            _check("Patient.gender", res.gender)
        for ident in getattr(res, "identifier", None) or []:
            _check("Identifier.use", ident.use)
    return b


def ems_uuid_from_bundle(b: Bundle) -> str | None:
    for entry in b.entry or []:
        if entry.resource.resource_type == "Encounter":
            for ident in entry.resource.identifier or []:
                if ident.system == EMS_UUID_SYSTEM:
                    return ident.value
    return None


def run(
    ems: pd.DataFrame,
    ed: pd.DataFrame,
    truth_links: pd.DataFrame,
    cfg: dict,
    rng: np.random.Generator,
    validate_all: bool = True,
) -> dict:
    pc = cfg["patterns"]["C_fhir_api"]
    ids = sorted(ems[ems.destination_code.notna()].ems_uuid)
    link_map = dict(zip(truth_links.ems_uuid, truth_links.ed_encounter_id, strict=True))
    ed_rows = {r.ed_encounter_id: r for r in ed.itertuples(index=False)}
    log = {"n_transported": len(ids)}

    enabled, _ = stage(rng, ids, pc["api_enabled"])
    success, _ = stage(rng, enabled, pc["api_call_success"])
    n_txn_validated = 0
    for u in success:  # each successful call carries a valid transaction Bundle
        b = validate(transaction_bundle(ed_rows[link_map[u]], u))
        assert ems_uuid_from_bundle(b) == u
        n_txn_validated += 1
    retained, _ = stage(rng, success, pc["identifier_retained"])
    log.update(
        {
            "api_enabled": len(enabled),
            "api_call_success": len(success),
            "identifier_retained": len(retained),
            "transaction_bundles_validated": n_txn_validated,
        }
    )
    carried = {link_map[u]: u for u in retained}

    out_uuid, n_valid = [], 0
    for r in ed.itertuples(index=False):
        raw = ed_record_bundle(r, carried.get(r.ed_encounter_id))
        if validate_all:
            out_uuid.append(ems_uuid_from_bundle(validate(raw)))
            n_valid += 1
        else:
            out_uuid.append(carried.get(r.ed_encounter_id))
    ed_out = ed.copy()
    ed_out["ems_uuid"] = out_uuid
    log["ed_record_bundles_validated"] = n_valid
    log["ed_records_with_uuid"] = int(ed_out.ems_uuid.notna().sum())
    log["expected_carry_rate"] = expected_carry_rate([pc[s] for s in STAGES])
    log["observed_carry_rate"] = len(retained) / max(1, len(ids))

    examples = []
    for u in sorted(retained)[: cfg["patterns"]["n_examples"]]:
        r = ed_rows[link_map[u]]
        examples.append(
            {
                "transaction_bundle": transaction_bundle(r, u),
                "ed_record_bundle": ed_record_bundle(r, u),
            }
        )
    return {"ed_records": ed_out, "log": log, "examples": examples}
