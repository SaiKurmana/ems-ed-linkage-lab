"""Small, verified code lists used by the synthetic generator.

ICD-10-CM codes and descriptions were checked against the CMS FY2026 ICD-10-CM code
descriptions file (icd10cm_codes_2026.txt, "2026 Code Descriptions in Tabular Order").
NEMSIS value labels were checked against the NEMSIS v3.5.0 Data Dictionary element pages.
See docs/standards_references.md for URLs and access dates.

Codes are stored without the decimal point (as in the CMS file); `dotted()` adds it.
"""

from __future__ import annotations

# --- External-cause codes (also valid values pattern for NEMSIS eInjury.01 Cause of Injury) ---
EXTERNAL_CAUSE = {
    "mvc": {
        "V4352XA": "Car driver injured in collision with other type car in traffic accident, initial encounter",
        "V499XXA": "Car occupant (driver) (passenger) injured in unspecified traffic accident, initial encounter",
        "V892XXA": "Person injured in unspecified motor-vehicle accident, traffic, initial encounter",
        "V0310XA": "Pedestrian on foot injured in collision with car, pick-up truck or van in traffic accident, initial encounter",
    },
    "fall": {
        "W010XXA": "Fall on same level from slipping, tripping and stumbling without subsequent striking against object, initial encounter",
        "W1830XA": "Fall on same level, unspecified, initial encounter",
        "W109XXA": "Fall (on) (from) unspecified stairs and steps, initial encounter",
        "W06XXXA": "Fall from bed, initial encounter",
        "W1789XA": "Other fall from one level to another, initial encounter",
        "W19XXXA": "Unspecified fall, initial encounter",
    },
}
EXTERNAL_CAUSE_WEIGHTS = {
    "mvc": [0.45, 0.25, 0.20, 0.10],
    "fall": [0.30, 0.15, 0.18, 0.10, 0.07, 0.20],
}

# --- Injury diagnosis codes by severity tier (simulation assumption, not clinical guidance) ---
INJURY_DX = {
    "minor": {
        "S0003XA": "Contusion of scalp, initial encounter",
        "S0083XA": "Contusion of other part of head, initial encounter",
        "S0101XA": "Laceration without foreign body of scalp, initial encounter",
        "S134XXA": "Sprain of ligaments of cervical spine, initial encounter",
        "S20219A": "Contusion of unspecified front wall of thorax, initial encounter",
        "S300XXA": "Contusion of lower back and pelvis, initial encounter",
        "S8000XA": "Contusion of unspecified knee, initial encounter",
    },
    "moderate": {
        "S060X0A": "Concussion without loss of consciousness, initial encounter",
        "S52501A": "Unspecified fracture of the lower end of right radius, initial encounter for closed fracture",
        "S52502A": "Unspecified fracture of the lower end of left radius, initial encounter for closed fracture",
        "S42001A": "Fracture of unspecified part of right clavicle, initial encounter for closed fracture",
        "S2231XA": "Fracture of one rib, right side, initial encounter for closed fracture",
        "S6290XA": "Unspecified fracture of unspecified hand, initial encounter for closed fracture",
        "S8290XA": "Unspecified fracture of unspecified lower leg, initial encounter for closed fracture",
    },
    "severe": {
        "S72001A": "Fracture of unspecified part of neck of right femur, initial encounter for closed fracture",
        "S72002A": "Fracture of unspecified part of neck of left femur, initial encounter for closed fracture",
        "S060X1A": "Concussion with loss of consciousness of 30 minutes or less, initial encounter",
        "S2241XA": "Multiple fractures of ribs, right side, initial encounter for closed fracture",
        "S3282XA": "Multiple fractures of pelvis without disruption of pelvic ring, initial encounter for closed fracture",
        "S82101A": "Unspecified fracture of upper end of right tibia, initial encounter for closed fracture",
        "S3210XA": "Unspecified fracture of sacrum, initial encounter for closed fracture",
    },
    "critical": {
        "S065X0A": "Traumatic subdural hemorrhage without loss of consciousness, initial encounter",
        "S069X9A": "Unspecified intracranial injury with loss of consciousness of unspecified duration, initial encounter",
        "S270XXA": "Traumatic pneumothorax, initial encounter",
        "S36116A": "Major laceration of liver, initial encounter",
        "S32810A": "Multiple fractures of pelvis with stable disruption of pelvic ring, initial encounter for closed fracture",
        "T07XXXA": "Unspecified multiple injuries, initial encounter",
    },
}
# Hip fractures (S72.00-) are concentrated in older-adult falls; head injuries span both.
FALL_PREFERRED = {
    "S72001A",
    "S72002A",
    "S52501A",
    "S52502A",
    "S0083XA",
    "S060X0A",
    "S065X0A",
    "S3210XA",
}
MVC_PREFERRED = {
    "S134XXA",
    "S20219A",
    "S2231XA",
    "S2241XA",
    "S270XXA",
    "S36116A",
    "S32810A",
    "T07XXXA",
    "S82101A",
}

ALL_ICD10CM = {
    **{c: d for m in EXTERNAL_CAUSE.values() for c, d in m.items()},
    **{c: d for tier in INJURY_DX.values() for c, d in tier.items()},
}


def dotted(code: str) -> str:
    """'S72001A' -> 'S72.001A' (ICD-10-CM display convention)."""
    return code if len(code) <= 3 else f"{code[:3]}.{code[3:]}"


# --- NEMSIS v3.5.0 value labels (verified from the data dictionary) ---
# eHistory.17 Alcohol/Drug Use Indicators
ALCOHOL_DRUG_POSITIVE = [
    "Alcohol Containers/Paraphernalia at Scene",
    "Drug Paraphernalia at Scene",
    "Patient Admits to Alcohol Use",
    "Patient Admits to Drug Use",
    "Physical Exam Indicates Suspected Alcohol or Drug Use",
]
ALCOHOL_DRUG_NONE = "None Reported"  # pertinent negative PN.NoneReported

# eInjury.03 Trauma Triage Criteria (High Risk for Serious Injury) — subset, non-deprecated
TRAUMA_HIGH_RISK = {
    "gcs": "Unable to follow commands (motor GCS < 6)",
    "skull": "Skull deformity, suspected skull fracture",
    "chest": "Chest wall instability, deformity, or suspected flail chest",
    "pelvis": "Suspected pelvic fracture",
    "long_bones": "Suspected fracture of two or more proximal long bones",
    "sbp_65": "Age >= 65 years: SBP < 110 mmHg",
    "sbp_adult": "Age 10-64 years: SBP < 90 mmHg",
    "rr": "RR < 10 or > 29 breaths/min",
}
# eInjury.04 Trauma Triage Criteria (Moderate Risk for Serious Injury) — subset, non-deprecated
TRAUMA_MODERATE_RISK = {
    "mvc": [
        "Auto Crash: Partial or complete ejection",
        "Auto Crash: Significant intrusion (including roof): >12 inches occupant site; >18 inches any site; need for extrication",
        "Pedestrian/bicycle rider thrown, run over, or with significant impact",
    ],
    "fall": [
        "Fall from height > 10 feet (all ages)",
        "Low-level falls in young children (age <= 5 years) or older adults (age >= 65 years) with significant head impact",
        "Anticoagulant use",
    ],
    "any": ["Other EMS judgment"],
}
NONE_REPORTED = "None Reported"

# eDisposition.30 Transport Disposition (subset)
TRANSPORT_THIS_UNIT = "Transport by This EMS Unit (This Crew Only)"
PATIENT_REFUSED = "Patient Refused Transport"
NO_TRANSPORT = "No Transport"
# eDisposition.27 Unit Disposition
PATIENT_CONTACT = "Patient Contact Made"

# ePatient.14 Race (NEMSIS combines Hispanic or Latino into the race list)
NEMSIS_RACE = {
    "White": "White",
    "Black": "Black or African American",
    "Hispanic": "Hispanic or Latino",
    "Asian": "Asian",
    "AIAN": "American Indian or Alaska Native",
    "NHPI": "Native Hawaiian or Other Pacific Islander",
}
NEMSIS_NOT_RECORDED = "Not Recorded"

# Simplified procedure labels. NEMSIS eProcedures.03 uses SNOMED CT codes; we do not
# reproduce SNOMED codes here — these are plain-text "simplified NEMSIS-inspired" labels.
PROCEDURES = [
    "Spinal motion restriction",
    "Splinting",
    "Peripheral IV access",
    "Bleeding control / wound care",
    "Airway management",
    "Pain management (medication)",
    "Cardiac monitoring",
]

# ED dispositions (simplified; see docs for mapping to eOutcome.01 / FHIR / HL7 v2)
ED_DISPOSITIONS = ["discharged", "admitted", "transferred", "died"]
