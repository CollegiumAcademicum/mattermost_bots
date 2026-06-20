#!/usr/bin/env python3
"""Quick smoke-test for LDAP connectivity and authentication.

Reads settings from the nearest .env (repo root or current directory).
For LDAPS, place ca.cert next to this script or set LDAP_CA_CERT_PATH in .env.

Usage:
    # Check service-account bind only:
    uv run scripts/check_ldap.py

    # Also search for a user and test their password:
    uv run scripts/check_ldap.py <username> [password]
"""

import os
import sys
from pathlib import Path

from dotenv import dotenv_values

# ── Load .env ─────────────────────────────────────────────────────────────────

_here = Path(__file__).resolve().parent
for _candidate in (_here.parent / ".env", _here / ".env"):
    if _candidate.exists():
        _env = dict(dotenv_values(_candidate))
        break
else:
    print("ERROR: no .env file found next to this script or in the repo root.")
    sys.exit(1)

def _get(key: str, default: str = "") -> str:
    return _env.get(key, default) or default

SERVER_URI       = _get("LDAP_SERVER_URI", "ldap://localhost")
BIND_DN          = _get("LDAP_BIND_DN")
BIND_PASSWORD    = _get("LDAP_BIND_PASSWORD")
USER_SEARCH_BASE = _get("LDAP_USER_SEARCH_BASE")
ADMIN_GROUP_DN   = _get("LDAP_ADMIN_GROUP_DN")
# CA cert: explicit env var, or fall back to ca.cert next to this script
CA_CERT_PATH     = _get("LDAP_CA_CERT_PATH") or str(_here / "ca.cert")

# ── Helpers ───────────────────────────────────────────────────────────────────

def ok(msg: str) -> None:
    print(f"  [OK]   {msg}")

def fail(msg: str) -> None:
    print(f"  [FAIL] {msg}")

def info(msg: str) -> None:
    print(f"         {msg}")

# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    username = sys.argv[1] if len(sys.argv) > 1 else None
    password = sys.argv[2] if len(sys.argv) > 2 else None

    try:
        import ldap
        import ldap.filter
    except ImportError:
        print("ERROR: python-ldap is not installed.")
        sys.exit(1)

    is_ldaps = SERVER_URI.startswith("ldaps://")

    print(f"\nLDAP smoke-test")
    print(f"  Server : {SERVER_URI}")
    print(f"  Bind DN: {BIND_DN or '(not set)'}")
    print(f"  Search : {USER_SEARCH_BASE or '(not set)'}")
    if is_ldaps:
        ca_exists = Path(CA_CERT_PATH).exists()
        print(f"  CA cert: {CA_CERT_PATH} ({'found' if ca_exists else 'NOT FOUND'})")
    print()

    # Step 1: connect (+ TLS setup for ldaps://)
    print("1. Connecting to server …")
    try:
        # Disable referral chasing — required for FreeIPA to avoid bind errors
        ldap.set_option(ldap.OPT_REFERRALS, 0)
        ldap.set_option(ldap.OPT_PROTOCOL_VERSION, ldap.VERSION3)

        if is_ldaps:
            if Path(CA_CERT_PATH).exists():
                abs_cert = str(Path(CA_CERT_PATH).resolve())
                try:
                    # Works on Linux (OpenSSL backend)
                    ldap.set_option(ldap.OPT_X_TLS_CACERTFILE, abs_cert)
                    ldap.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, ldap.OPT_X_TLS_DEMAND)
                    ldap.set_option(ldap.OPT_X_TLS_NEWCTX, 0)
                except ValueError:
                    # macOS Secure Transport backend ignores OPT_X_TLS_CACERTFILE
                    # and LDAPTLS_CACERT — skip verification (dev only).
                    info("macOS detected: cert verification not supported via python-ldap.")
                    info("Continuing without verification (credentials still tested).")
                    ldap.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, ldap.OPT_X_TLS_NEVER)
                    ldap.set_option(ldap.OPT_X_TLS_NEWCTX, 0)
            else:
                info("CA cert not found — skipping certificate verification (insecure).")
                ldap.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, ldap.OPT_X_TLS_NEVER)
                ldap.set_option(ldap.OPT_X_TLS_NEWCTX, 0)

        conn = ldap.initialize(SERVER_URI)
        conn.set_option(ldap.OPT_NETWORK_TIMEOUT, 5)
        conn.set_option(ldap.OPT_TIMEOUT, 5)

        ok(f"Connected to {SERVER_URI}")
    except Exception as exc:
        fail(f"Could not initialise connection: {exc}")
        sys.exit(1)

    # Step 2: service-account bind
    print("2. Binding with service account …")
    if not BIND_DN:
        fail("LDAP_BIND_DN is not set — skipping bind.")
    else:
        try:
            conn.simple_bind_s(BIND_DN, BIND_PASSWORD)
            ok(f"Bind successful as {BIND_DN}")
        except ldap.INVALID_CREDENTIALS:
            fail("Bind failed: invalid credentials (wrong DN or password).")
            sys.exit(1)
        except ldap.SERVER_DOWN:
            fail("Server unreachable.")
            sys.exit(1)
        except Exception as exc:
            fail(f"Bind error: {exc}")
            sys.exit(1)

    # Step 3: search for user (optional)
    if username:
        print(f"3. Searching for user '{username}' …")
        if not USER_SEARCH_BASE:
            fail("LDAP_USER_SEARCH_BASE is not set — skipping search.")
        else:
            try:
                results = conn.search_s(
                    USER_SEARCH_BASE,
                    ldap.SCOPE_SUBTREE,
                    f"(uid={ldap.filter.escape_filter_chars(username)})",
                    ["dn", "cn", "mail", "givenName", "sn", "memberOf"],
                )
                if not results:
                    fail(f"No entry found for uid={username} under {USER_SEARCH_BASE}")
                    sys.exit(1)

                user_dn, attrs = results[0]
                ok(f"Found: {user_dn}")
                for attr in ("cn", "mail", "givenName", "sn"):
                    val = attrs.get(attr, [b""])[0]
                    if val:
                        info(f"{attr}: {val.decode()}")

                # List all groups
                member_of = [v.decode() for v in attrs.get("memberOf", [])]
                if member_of:
                    info("Groups:")
                    for g in sorted(member_of):
                        info(f"  {g}")
                else:
                    info("No groups found (memberOf attribute empty or not returned).")

                # Check admin group membership
                if ADMIN_GROUP_DN:
                    if ADMIN_GROUP_DN in member_of:
                        ok(f"Member of admin group ({ADMIN_GROUP_DN})")
                    else:
                        info(f"NOT a member of admin group ({ADMIN_GROUP_DN})")

            except Exception as exc:
                fail(f"Search error: {exc}")
                sys.exit(1)

        # Step 4: authenticate as user (optional)
        if password:
            print(f"4. Authenticating as '{username}' …")
            try:
                user_conn = ldap.initialize(SERVER_URI)
                user_conn.set_option(ldap.OPT_NETWORK_TIMEOUT, 5)
                if is_ldaps:
                    user_conn.set_option(ldap.OPT_X_TLS_NEWCTX, 0)
                user_conn.simple_bind_s(user_dn, password)
                ok(f"Authentication successful for {username}")
            except ldap.INVALID_CREDENTIALS:
                fail("Authentication failed: wrong password.")
            except Exception as exc:
                fail(f"Authentication error: {exc}")

    print()


if __name__ == "__main__":
    main()
