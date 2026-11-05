"""Minimal HL7 v2.5.1 ADT message builder + parser (python-hl7) used by patterns A and B.

Only segments/fields verified against HL7 public sources are populated
(see docs/standards_references.md):

  MSH-9  Message Type           e.g. ADT^A05^ADT_A05 (Table 0003 event, Table 0354 structure)
  MSH-10 Message Control ID
  MSH-11 Processing ID          "T" (Training) — these are synthetic messages
  MSH-12 Version ID             2.5.1
  EVN    Event type segment
  PID-3  Patient Identifier List (CX; type code from Table 0203: MR, PI)
  PID-5  Patient Name (XPN)       PID-7 Date/Time of Birth   PID-8 Administrative Sex (Table 0001)
  PID-10 Race (CWE, text only)    PID-22 Ethnic Group (CWE, text only)
  PV1-2  Patient Class (Table 0004: E = Emergency)
  PV1-3  Assigned Patient Location
  PV1-19 Visit Number (CX, type VN)
  PV1-37 Discharged to Location (used by EMS for the destination facility)
  PV1-44 Admit Date/Time          PV1-45 Discharge Date/Time
  PV1-50 Alternate Visit ID (CX)  <-- where the EMS UUID lives in the ED record (local convention)
  PV2-38 Mode of Arrival Code (Table 0430: A = Ambulance, C = Car, F = On foot)
"""

from __future__ import annotations

from datetime import datetime

import hl7
import pandas as pd

from common import EMS_UUID_ASSIGNING_AUTHORITY

SEP = "\r"
ARRIVAL_TEXT = {"A": "Ambulance", "C": "Car", "F": "On foot", "H": "Helicopter", "U": "Unknown"}
SEX_V2 = {"Female": "F", "Male": "M", "F": "F", "M": "M"}


def ts(x) -> str:
    if x is None or (isinstance(x, float) and pd.isna(x)) or pd.isna(x):
        return ""
    if isinstance(x, str):
        x = datetime.fromisoformat(x)
    return x.strftime("%Y%m%d%H%M%S")


def dob(x) -> str:
    return "" if not x or pd.isna(x) else str(x).replace("-", "")


def esc(s) -> str:
    """Escape HL7 delimiters in free text (|, ^, ~, \\, &)."""
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return ""
    s = str(s)
    return (
        s.replace("\\", "\\E\\")
        .replace("|", "\\F\\")
        .replace("^", "\\S\\")
        .replace("~", "\\R\\")
        .replace("&", "\\T\\")
    )


def msh(sending_app, sending_fac, recv_app, recv_fac, when, event, structure, control_id) -> str:
    return (
        f"MSH|^~\\&|{sending_app}|{sending_fac}|{recv_app}|{recv_fac}|{ts(when)}||"
        f"ADT^{event}^{structure}|{control_id}|T|2.5.1"
    )


def pid(
    identifier: str,
    assigning_authority: str,
    id_type: str,
    last,
    first,
    birth,
    sex,
    race=None,
    ethnicity=None,
) -> str:
    fields = [""] * 23
    fields[0] = "PID"
    fields[1] = "1"
    fields[3] = f"{esc(identifier)}^^^{assigning_authority}^{id_type}"
    fields[5] = f"{esc(last)}^{esc(first)}"
    fields[7] = dob(birth)
    fields[8] = SEX_V2.get(sex, "U") if sex else "U"
    if race:
        fields[10] = f"^{esc(race)}"
    if ethnicity:
        fields[22] = f"^{esc(ethnicity)}"
    return "|".join(fields).rstrip("|")


def pv1(
    location_facility=None,
    visit_number=None,
    visit_aa=None,
    discharged_to=None,
    admit_ts=None,
    discharge_ts=None,
    ems_uuid=None,
) -> str:
    f = [""] * 51
    f[0] = "PV1"
    f[1] = "1"
    f[2] = "E"
    if location_facility:
        f[3] = f"ED^^^{location_facility}"
    if visit_number:
        f[19] = f"{visit_number}^^^{visit_aa}^VN"
    if discharged_to:
        f[37] = discharged_to
    f[44] = ts(admit_ts)
    f[45] = ts(discharge_ts)
    if ems_uuid:
        f[50] = f"{ems_uuid}^^^{EMS_UUID_ASSIGNING_AUTHORITY}^VN"
    return "|".join(f).rstrip("|")


def pv2(arrival_mode: str | None) -> str:
    if not arrival_mode:
        return ""
    f = [""] * 39
    f[0] = "PV2"
    f[38] = f"{arrival_mode}^{ARRIVAL_TEXT.get(arrival_mode, '')}^HL70430"
    return "|".join(f)


def evn(event: str, when) -> str:
    return f"EVN|{event}|{ts(when)}"


def join(*segments: str) -> str:
    return SEP.join(s for s in segments if s) + SEP


# ----------------------------------------------------------------------------- parsing
def parse(message: str) -> hl7.Message:
    return hl7.parse(message)


def _field(msg: hl7.Message, seg: str, idx: int) -> str:
    try:
        return str(msg.segment(seg)[idx])
    except (KeyError, IndexError):
        return ""


def cx_parts(value: str) -> list[str]:
    return value.split("^") if value else []


def extract_ems_uuid(msg: hl7.Message, field: tuple[str, int] = ("PV1", 50)) -> str | None:
    """Return the EMS UUID from a CX field if its assigning authority is EMSUUID."""
    raw = _field(msg, *field)
    for rep in raw.split("~"):
        parts = cx_parts(rep)
        if len(parts) >= 4 and parts[3] == EMS_UUID_ASSIGNING_AUTHORITY and parts[0]:
            return parts[0]
    return None


def message_type(msg: hl7.Message) -> str:
    return _field(msg, "MSH", 9)


def field(msg: hl7.Message, seg: str, idx: int) -> str:
    return _field(msg, seg, idx)


def pretty(message: str) -> str:
    """Human-readable form (one segment per line) for examples/."""
    return message.replace(SEP, "\n")
