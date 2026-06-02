"""
Run once to populate the database with test parts and API keys.
Usage: python scripts/seed.py
"""
import hashlib
import sys
import os


from registry.db import get_conn, release_conn


PARTS = [
    # Honda
    ("P-1001", "Honda",   "Civic",    "Oil Filter",       "2018-2023 Civic, 2019-2022 Insight",          True),
    ("P-1002", "Honda",   "Accord",   "Drive Belt",       "2016-2022 Accord, 2017-2021 CR-V",            True),
    ("P-1003", "Honda",   "CR-V",     "Brake Pad",        "2017-2022 CR-V, 2018-2022 HR-V",              True),
    ("P-1004", "Honda",   "Pilot",    "Air Filter",       "2016-2022 Pilot, 2017-2022 Ridgeline",        True),
    ("P-1005", "Honda",   "Odyssey",  "Spark Plug",       "2018-2023 Odyssey",                           True),
    # Toyota
    ("P-2001", "Toyota",  "Camry",    "Brake Pad",        "2017-2023 Camry, 2018-2022 Avalon",           True),
    ("P-2002", "Toyota",  "Corolla",  "Oil Filter",       "2019-2023 Corolla, 2019-2022 Matrix",         True),
    ("P-2003", "Toyota",  "RAV4",     "Battery",          "2018-2023 RAV4, 2021-2023 RAV4 Prime",        True),
    ("P-2004", "Toyota",  "Tacoma",   "Shock Absorber",   "2016-2023 Tacoma",                            True),
    ("P-2005", "Toyota",  "Highlander","Cabin Air Filter", "2017-2022 Highlander",                       True),
    # Ford
    ("P-3001", "Ford",    "F-150",    "Battery",          "2015-2023 F-150",                             True),
    ("P-3002", "Ford",    "Mustang",  "Brake Rotor",      "2018-2023 Mustang GT, 2020-2023 Mustang EcoBoost", True),
    ("P-3003", "Ford",    "Explorer", "Transmission Filter","2016-2022 Explorer",                        True),
    ("P-3004", "Ford",    "Escape",   "Fuel Filter",      "2017-2022 Escape, 2020-2022 Escape Hybrid",   True),
    ("P-3005", "Ford",    "Ranger",   "Spark Plug",       "2019-2023 Ranger",                            True),
    # GM
    ("P-4001", "Chevrolet","Silverado","Oil Filter",      "2014-2023 Silverado 1500, 2015-2023 Silverado 2500", True),
    ("P-4002", "Chevrolet","Equinox",  "Brake Pad",       "2018-2022 Equinox",                           True),
    ("P-4003", "GMC",     "Sierra",   "Air Filter",       "2014-2023 Sierra 1500",                       True),
    ("P-4004", "Chevrolet","Malibu",  "Alternator",       "2016-2022 Malibu",                            True),
    # Imports
    ("P-5001", "BMW",     "3 Series", "Brake Pad",        "2018-2023 330i, 2019-2023 M340i",             True),
    ("P-5002", "Mercedes","C-Class",  "Oil Filter",       "2019-2023 C300, 2020-2023 C43 AMG",           True),
    ("P-5003", "Subaru",  "Outback",  "Timing Belt Kit",  "2015-2019 Outback 2.5i",                      True),
    ("P-5004", "Hyundai", "Elantra",  "Spark Plug",       "2017-2022 Elantra",                           True),
    ("P-5005", "Kia",     "Sportage", "Cabin Air Filter", "2017-2022 Sportage",                          True),
    # Retired / discontinued
    ("P-9001", "Pontiac", "G6",       "Brake Pad",        "2005-2010 G6 — Discontinued",                 False),
    ("P-9002", "Saturn",  "Vue",      "Oil Filter",       "2002-2010 Vue — Discontinued",                False),
    ("P-9999", "Legacy",  "Retired",  "Filter",           "Discontinued",                                False),
]

# Plain-text keys shown here for seeding only — store only the hash in production
API_KEYS = [
    ("finance",    "sk-finance-team-key-001",    ["read:parts", "validate:parts"], 10000),
    ("compliance", "sk-compliance-team-key-002", ["validate:parts"],               5000),
    ("ml-team",    "sk-ml-team-key-003",         ["read:parts"],                   50000),
    ("admin",      "sk-admin-key-004",           ["read:parts", "validate:parts", "admin"], 999999),
]


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def seed():
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            for part in PARTS:
                cur.execute(
                    """
                    INSERT INTO parts (part_number, make, model, category, compatibility, is_valid)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (part_number) DO NOTHING
                    """,
                    part
                )

            for team, plain_key, scopes, rate_limit in API_KEYS:
                cur.execute(
                    """
                    INSERT INTO api_keys (team, key_hash, scopes, rate_limit)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (key_hash) DO NOTHING
                    """,
                    (team, hash_key(plain_key), scopes, rate_limit)
                )

        conn.commit()
        print("Seeded parts and API keys.")
        print("\nTest API keys:")
        for team, key, scopes, _ in API_KEYS:
            print(f"  {team}: {key}  scopes={scopes}")

    finally:
        release_conn(conn)


if __name__ == "__main__":
    seed()
