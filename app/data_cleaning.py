import re
import pandas as pd

CANADIAN_PROVINCES = {
    "AB", "BC", "MB", "NB", "NL", "NS", "NT", "NU", "ON", "PE", "QC", "SK", "YT",
}

# Word-boundary abbreviations, applied to BOTH the fuel CSV and GeoNames
# so the two sides normalize to the same string.
_ABBREVIATIONS = [
    (re.compile(r"\bst\b"), "saint"),
    (re.compile(r"\bmt\b"), "mount"),
    (re.compile(r"\bft\b"), "fort"),
]


def normalize_city(name: str) -> str:
    """'St. Louis ' -> 'saint louis'. Use on both sides before matching."""
    name = str(name).lower().strip()
    name = name.replace(".", " ").replace("'", "")
    name = re.sub(r"\s+", " ", name).strip()
    for pattern, replacement in _ABBREVIATIONS:
        name = pattern.sub(replacement, name)
    return re.sub(r"[^a-z0-9]", "", name)


def clean_fuel_data(csv_path: str) -> pd.DataFrame:
    """Load the fuel CSV and return it cleaned."""
    df = pd.read_csv(csv_path)

    # Rename columns
    df = df.rename(columns={
        "OPIS Truckstop ID": "stop_id",
        "Truckstop Name": "name",
        "Address": "address",
        "City": "city",
        "State": "state",
        "Rack ID": "rack_id",
        "Retail Price": "price",
    })

    
    for col in ("name", "address", "city", "state"):
        df[col] = df[col].astype(str).str.strip()
    df["state"] = df["state"].str.upper()

    # drop rows with a missing or invalid price
    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    df = df.dropna(subset=["price"])
    df = df[df["price"] > 0]

    # drop Canadian rows (route is USA-only)
    df = df[~df["state"].isin(CANADIAN_PROVINCES)]

    # One row per stop: keep the lowest price for each stop_id
    df = df.loc[df.groupby("stop_id")["price"].idxmin()]

    # Normalized city key, used later to join with GeoNames
    df["city_key"] = df["city"].map(normalize_city)

    return df.reset_index(drop=True)