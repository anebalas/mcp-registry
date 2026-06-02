"""
Run once to populate the database with test parts and API keys.
Usage: python scripts/seed.py
"""
import hashlib
import sys
import os


from registry.db import get_conn, release_conn


PARTS = [
    ("P-1001", "Honda",  "Civic",   "Filter",   "2018-2023 Civic, 2019-2022 Insight", True),
    ("P-1002", "Toyota", "Camry",   "Brake Pad","2017-2023 Camry, 2018-2022 Avalon",  True),
    ("P-1003", "Ford",   "F-150",   "Battery",  "2015-2023 F-150",                    True),
    ("P-1004", "Honda",  "Accord",  "Belt",     "2016-2022 Accord",                   True),
    ("P-9999", "Legacy", "Retired", "Filter",   "Discontinued",                       False),
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
