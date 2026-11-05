"""Shared helpers for the EMS–ED Linkage Lab (synthetic data only)."""

DISCLAIMER = "Synthetic data — for demonstration only."
AFFILIATION = (
    "Independent portfolio project. Not affiliated with, endorsed by, or produced for the CDC, "
    "NHTSA, NEMSIS, or any agency. All data are synthetic."
)

# Identifier namespace used for the EMS UUID when it is carried into hospital systems.
# example.org is reserved for documentation (RFC 2606); a real deployment would use a URI
# owned and governed by the state EMS office or HIE.
EMS_UUID_SYSTEM = "https://ems-ed-linkage-lab.example.org/fhir/sid/ems-pcr-uuid"
HOSPITAL_VISIT_SYSTEM_TMPL = "https://ems-ed-linkage-lab.example.org/fhir/sid/{hospital}/visit"
HOSPITAL_MRN_SYSTEM_TMPL = "https://ems-ed-linkage-lab.example.org/fhir/sid/{hospital}/mrn"
# HL7 v2 assigning-authority namespace for the EMS UUID in PV1-50 (local convention)
EMS_UUID_ASSIGNING_AUTHORITY = "EMSUUID"
