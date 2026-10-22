"""AAMVA PDF417 barcode encoder compliant with AAMVA DL/ID-2016/2020 standard."""

from datetime import datetime
from typing import Optional

PDF_LINEFEED = "\n"
PDF_RECORDSEP = "\x1e"
PDF_SEGTERM = "\r"
PDF_FILETYPE = "ANSI "

# AAMVA field definitions for v9/v10 (2016/2020)
REQUIRED_FIELDS_V9 = {
    "DCS": "last_name",      # Customer family name
    "DAC": "first_name",     # Customer given name
    "DAD": "middle_name",    # Customer middle name(s)
    "DBD": "issue_date",     # Document issue date (YYYYMMDD)
    "DBB": "dob",            # Date of birth (YYYYMMDD)
    "DBA": "expiry_date",    # Document expiration date (YYYYMMDD)
    "DBC": "sex",            # Sex (1=M, 2=F, 9=X)
    "DAY": "eye_color",      # Eye color code
    "DAU": "height",         # Height (e.g., "71 in" or "180 cm")
    "DAG": "address",        # Address line 1
    "DAI": "city",           # City
    "DAJ": "state",          # State/province (2 chars)
    "DAK": "zip",            # Postal code
    "DAQ": "license_number", # License number
    "DCF": "document_number",# Document discriminator
    "DCG": "country",        # Country code (USA/CAN)
    "DCA": "license_class",  # License class
    "DCB": "restrictions",   # Restriction codes
    "DCD": "endorsements",   # Endorsement codes
}

OPTIONAL_FIELDS_V9 = {
    "DAH": "address2",       # Address line 2
    "DAZ": "hair_color",     # Hair color code
    "DCU": "suffix",         # Name suffix
    "DDE": "last_name_trunc",# Last name truncated (T/F)
    "DDF": "first_name_trunc",# First name truncated (T/F)
    "DDG": "middle_name_trunc",# Middle name truncated (T/F)
    "DCE": "weight_range",   # Weight range (0-9)
    "DDL": "weight_range_v10", # Weight range v10 (0-9)
    "DAW": "weight_lbs",     # Weight in pounds
    "DAX": "weight_kg",      # Weight in kg
    "DDH": "under18_until",  # Under 18 until date
    "DDI": "under19_until",  # Under 19 until date
    "DDJ": "under21_until",  # Under 21 until date
    "DCK": "inventory_num",  # Inventory control number
    "DDA": "compliance_type",# Compliance type
    "DDB": "card_revision",  # Card revision date
    "DDC": "hazmat_expiry",  # Hazmat expiration
    "DDD": "limited_duration",# Limited duration indicator
    "DCI": "jurisdiction",   # Jurisdiction-specific
    "DDK": "organ_donor",    # Organ donor indicator
    "DCK": "inventory_num",  # Inventory control
}

EYE_COLORS = ["BLK", "BLU", "BRO", "GRY", "HAZ", "MAR", "PNK", "DIC", "UNK", "GRN"]
HAIR_COLORS = ["BAL", "BLK", "BLN", "BRO", "GRY", "RED", "SDY", "WHI", "UNK"]

SEX_MAP = {"M": "1", "F": "2", "X": "9", "MALE": "1", "FEMALE": "2", "UNSPECIFIED": "9"}


def _validate_eye(code: str) -> str:
    code = code.strip().upper()[:3]
    return code if code in EYE_COLORS else "UNK"


def _validate_hair(code: str) -> str:
    code = code.strip().upper()[:3]
    return code if code in HAIR_COLORS else "UNK"


def _validate_sex(code: str) -> str:
    code = code.strip().upper()[:1]
    return SEX_MAP.get(code, "9")


def _format_height(val: str) -> str:
    """Normalize height to 'NNN in' or 'NNN cm'."""
    val = val.strip().lower()
    if val.endswith("in") or val.endswith("\"") or val.endswith("inches"):
        num = "".join(c for c in val if c.isdigit())
        return f"{int(num):03d} in"
    if val.endswith("cm") or "cm" in val:
        num = "".join(c for c in val if c.isdigit())
        return f"{int(num):03d} cm"
    # Assume inches if just a number
    num = "".join(c for c in val if c.isdigit())
    if num:
        return f"{int(num):03d} in"
    return "000 in"


def _format_date(val: str, country: str = "USA") -> str:
    """Normalize date to MMDDYYYY for USA, YYYYMMDD for CAN/ISO."""
    val = "".join(c for c in val if c.isdigit())
    if len(val) == 8:
        # Assume input is YYYYMMDD, convert to MMDDYYYY for USA
        if country.upper() == "USA":
            return val[4:8] + val[0:2] + val[2:4]  # YYYYMMDD -> MMDDYYYY
        return val  # ISO/CAN uses YYYYMMDD
    # Try common formats
    for fmt in ("%Y%m%d", "%m%d%Y", "%d%m%Y", "%Y-%m-%d", "%m-%d-%Y"):
        try:
            dt = datetime.strptime(val, fmt)
            if country.upper() == "USA":
                return dt.strftime("%m%d%Y")
            return dt.strftime("%Y%m%d")
        except ValueError:
            pass
    return "01011900" if country.upper() == "USA" else "19000101"


def _pad_right(val: str, width: int) -> str:
    return (val + " " * width)[:width]


def build_aamva_string(
    *,
    iin: str = "636000",
    version: int = 9,
    jurisdiction_version: int = 0,
    state: str = "XX",
    zip_code: str = "00000",
    last_name: str = "LAST",
    first_name: str = "FIRST",
    middle_name: str = "",
    dob: str = "19800101",
    sex: str = "M",
    height: str = "70 in",
    weight: str = "180",
    eyes: str = "BRO",
    hair: str = "BLK",
    address: str = "123 MAIN ST",
    city: str = "CITY",
    expiry: str = "20300101",
    issued: str = "20200101",
    license_number: str = "LIC123",
    document_number: str = "DOC123",
    country: str = "USA",
    license_class: str = "D",
    restrictions: str = "",
    endorsements: str = "",
    address2: str = "",
    suffix: str = "",
    weight_range: str = "",
    organ_donor: str = "",
    **extra,
) -> str:
    """Build a compliant AAMVA v9/v10 PDF417 data string."""
    # Normalize inputs
    state = state.upper()[:2].ljust(2)
    zip_code = zip_code[:11].ljust(11)
    country = country.upper()[:3].ljust(3)
    license_class = license_class[:2].ljust(2)
    restrictions = restrictions[:10].ljust(10)
    endorsements = endorsements[:4].ljust(4)

    sex_code = _validate_sex(sex)
    eyes_code = _validate_eye(eyes)
    hair_code = _validate_hair(hair)
    height_fmt = _format_height(height)
    dob_fmt = _format_date(dob, country)
    expiry_fmt = _format_date(expiry, country)
    issued_fmt = _format_date(issued, country)

    # Build subfile data lines
    lines = []

    # Required fields
    lines.append(f"DCS{last_name.upper()}")
    lines.append(f"DAC{first_name.upper()}")
    if middle_name:
        lines.append(f"DAD{middle_name.upper()}")
    else:
        lines.append("DAD")
    lines.append(f"DBD{issued_fmt}")
    lines.append(f"DBB{dob_fmt}")
    lines.append(f"DBA{expiry_fmt}")
    lines.append(f"DBC{sex_code}")
    lines.append(f"DAY{eyes_code}")
    lines.append(f"DAU{height_fmt}")
    lines.append(f"DAG{address.upper()}")
    lines.append(f"DAI{city.upper()}")
    lines.append(f"DAJ{state}")
    lines.append(f"DAK{zip_code}")
    lines.append(f"DAQ{license_number.upper()}")
    lines.append(f"DCF{document_number.upper()}")
    lines.append(f"DCG{country}")
    lines.append(f"DCA{license_class}")
    lines.append(f"DCB{restrictions}")
    lines.append(f"DCD{endorsements}")

    # Optional fields
    if address2:
        lines.append(f"DAH{address2.upper()}")
    if hair:
        lines.append(f"DAZ{hair_code}")
    if suffix:
        lines.append(f"DCU{suffix.upper()}")
    if weight_range:
        lines.append(f"DDL{weight_range[:1]}")
    if organ_donor:
        lines.append(f"DDK{organ_donor[:1]}")

    for code, val in extra.items():
        if val:
            lines.append(f"{code}{val}")

    subfile_data = PDF_LINEFEED.join(lines)

    # Build subfile record with "DL" prefix and CR terminator
    subfile_record = "DL" + subfile_data + PDF_SEGTERM
    sub_len = len(subfile_record)

    # Build header
    ver_str = f"{version:02d}"
    juris_ver = f"{jurisdiction_version:02d}"
    n_entries = "01"

    header_prefix = f"{PDF_FILETYPE}{iin}{ver_str}{juris_ver}{n_entries}DL"
    # Header structure: @ + LF + RS + CR + header_prefix + offset(4) + length(4)
    header_base = f"@{PDF_LINEFEED}{PDF_RECORDSEP}{PDF_SEGTERM}{header_prefix}"
    # Offset is from start of data (after @\n\x1e\r) to start of subfile "DL"
    offset = len(header_base) + 8  # header_base + offset(4) + length(4)
    offset_str = f"{offset:04d}"
    length_str = f"{sub_len:04d}"

    full_header = f"{header_base}{offset_str}{length_str}"
    # Full data: header + subfile_record + CR + CR + LF (standard ending)
    full_data = f"{full_header}{subfile_record}{PDF_SEGTERM}{PDF_SEGTERM}{PDF_LINEFEED}"

    return full_data


def encode_to_png(
    data: str,
    columns: int = 6,
    security_level: int = 2,
    scale: int = 3,
    ratio: int = 3,
) -> bytes:
    """Encode AAMVA string to PNG bytes using pdf417gen."""
    try:
        import pdf417gen
    except ImportError:
        raise RuntimeError("pdf417gen not installed")
    codes = pdf417gen.encode(data, columns=columns, security_level=security_level)
    img = pdf417gen.render_image(codes, scale=scale, ratio=ratio)
    import io
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()