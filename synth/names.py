"""Synthetic name generation and name-variant logic.

Names come from Faker (seeded) plus small generic surname/given-name lists. They are
random combinations and do not describe real people.
"""

from __future__ import annotations

import unicodedata

import numpy as np
from faker import Faker

NICKNAMES = {
    "WILLIAM": ["BILL", "WILL", "BILLY"], "ROBERT": ["BOB", "ROB", "BOBBY"],
    "RICHARD": ["RICK", "DICK", "RICH"], "JAMES": ["JIM", "JIMMY"], "JOHN": ["JACK", "JOHNNY"],
    "JOSEPH": ["JOE", "JOEY"], "MICHAEL": ["MIKE", "MICKEY"], "THOMAS": ["TOM", "TOMMY"],
    "CHRISTOPHER": ["CHRIS"], "DANIEL": ["DAN", "DANNY"], "MATTHEW": ["MATT"],
    "ANTHONY": ["TONY"], "STEVEN": ["STEVE"], "EDWARD": ["ED", "EDDIE"], "CHARLES": ["CHUCK", "CHARLIE"],
    "ELIZABETH": ["LIZ", "BETH", "BETTY"], "MARGARET": ["PEGGY", "MAGGIE"], "PATRICIA": ["PAT", "TRISH"],
    "JENNIFER": ["JEN", "JENNY"], "KATHERINE": ["KATE", "KATHY"], "SUSAN": ["SUE"],
    "DEBORAH": ["DEB", "DEBBIE"], "REBECCA": ["BECKY"], "BARBARA": ["BARB"], "VICTORIA": ["VICKY"],
    "JOSE": ["PEPE"], "FRANCISCO": ["PANCHO", "PACO"], "GUADALUPE": ["LUPE"], "ALEJANDRO": ["ALEX"],
    "ROBERTO": ["BETO"], "ALBERTO": ["BETO"], "EDUARDO": ["LALO"], "JESUS": ["CHUY"],
    "IGNACIO": ["NACHO"], "ROSARIO": ["CHARO"], "CONCEPCION": ["CONCHA"], "DOLORES": ["LOLA"],
}

ASIAN_SURNAMES = ["NGUYEN", "TRAN", "LE", "PHAM", "KIM", "LEE", "PARK", "CHOI", "WANG", "LI",
                  "ZHANG", "CHEN", "LIU", "PATEL", "SHAH", "SINGH", "KUMAR", "SANTOS", "REYES", "CRUZ",
                  "TANAKA", "SATO", "HUANG", "WU", "VO"]
ASIAN_GIVEN = ["MINH", "THANH", "LINH", "HOA", "JI WOO", "MIN JUN", "SEO YEON", "WEI", "MING",
               "XIAO", "PRIYA", "ANIL", "RAVI", "DEEPA", "MARIA", "JOSE", "HIROSHI", "YUKI", "KENJI",
               "MEI", "AN", "DUC", "HUONG", "SUNIL", "ANJALI"]
NHPI_SURNAMES = ["KEALOHA", "KAHANANUI", "MAKOA", "TAUFA", "FIFITA", "TUIASOSOPO", "SALAVE'A",
                 "AKANA", "PALAKIKO", "LEAUPEPE", "KALEO", "MAHOE"]
NHPI_GIVEN = ["KEOLA", "MALIA", "LEILANI", "KAWIKA", "SIONE", "LOSA", "MANU", "NOELANI", "IOANE",
              "KALANI", "MELE", "TEVITA"]


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


class NameFactory:
    def __init__(self, seed: int, rng: np.random.Generator):
        self.rng = rng
        self.en = Faker("en_US")
        self.en.seed_instance(seed)
        self.es = Faker("es_MX")
        self.es.seed_instance(seed + 1)

    def make(self, race_eth: str, sex: str) -> tuple[str, str]:
        """Return (first, last) in upper case (accents preserved for Hispanic names)."""
        r = self.rng
        female = sex == "F"
        if race_eth == "Hispanic":
            first = self.es.first_name_female() if female else self.es.first_name_male()
            last = self.es.last_name()
            if r.random() < 0.45:  # compound (paternal + maternal) surname
                last = f"{last} {self.es.last_name()}"
        elif race_eth == "Asian":
            first = ASIAN_GIVEN[r.integers(len(ASIAN_GIVEN))]
            last = ASIAN_SURNAMES[r.integers(len(ASIAN_SURNAMES))]
        elif race_eth == "NHPI":
            first = NHPI_GIVEN[r.integers(len(NHPI_GIVEN))]
            last = NHPI_SURNAMES[r.integers(len(NHPI_SURNAMES))]
        else:
            first = self.en.first_name_female() if female else self.en.first_name_male()
            last = self.en.last_name()
            if r.random() < 0.04:
                last = f"{last}-{self.en.last_name()}"
        return first.upper(), last.upper()


def name_variant(first: str, last: str, race_eth: str, rng: np.random.Generator) -> tuple[str, str]:
    """Apply one plausible, non-typo name variation."""
    options = []
    if first in NICKNAMES:
        options.append("nickname")
    if " " in last or "-" in last:
        options.append("compound")
    if race_eth == "Asian":
        options.append("swap")
    if " " in first:
        options.append("given_space")
    options.append("accent_or_initial")
    choice = options[rng.integers(len(options))]
    if choice == "nickname":
        nicks = NICKNAMES[first]
        return nicks[rng.integers(len(nicks))], last
    if choice == "compound":
        parts = last.replace("-", " ").split()
        pick = rng.integers(3)
        if pick == 0:
            return first, parts[0]
        if pick == 1:
            return first, parts[-1]
        return first, "-".join(parts)
    if choice == "swap":
        return last, first
    if choice == "given_space":
        return first.replace(" ", rng.choice(["", "-"])), last
    # accent stripping is neutralised by standardisation, so fall back to first-initial-only
    if rng.random() < 0.5:
        return strip_accents(first), strip_accents(last)
    return first[0], last


KEYBOARD_NEIGHBORS = {
    "A": "QSZ", "B": "VNG", "C": "XVD", "D": "SFE", "E": "WRD", "F": "DGR", "G": "FHT", "H": "GJY",
    "I": "UOK", "J": "HKU", "K": "JLI", "L": "KO", "M": "NJ", "N": "BMH", "O": "IPL", "P": "OL",
    "Q": "WA", "R": "ETF", "S": "ADW", "T": "RYG", "U": "YIJ", "V": "CBF", "W": "QES", "X": "ZCS",
    "Y": "TUH", "Z": "XA",
}


def typo(s: str, rng: np.random.Generator) -> str:
    if len(s) < 2:
        return s
    i = int(rng.integers(len(s)))
    kind = rng.integers(4)
    if kind == 0:  # substitution with keyboard neighbour
        c = s[i]
        nb = KEYBOARD_NEIGHBORS.get(c)
        if not nb:
            return s
        return s[:i] + nb[rng.integers(len(nb))] + s[i + 1 :]
    if kind == 1:  # deletion
        return s[:i] + s[i + 1 :]
    if kind == 2 and i < len(s) - 1:  # transposition
        return s[:i] + s[i + 1] + s[i] + s[i + 2 :]
    return s[:i] + s[i] + s[i:]  # doubled letter
