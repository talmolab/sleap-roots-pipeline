#!/usr/bin/env bash
# 7.4b helper: dispatch a Bloom-side pipeline run and verify it by artifact.
#
# SECRET HANDLING (the reason this is a script rather than inline commands):
#   - The credentials file is read into shell variables and NEVER echoed.
#   - The minted JWT is written to $TOKEN_FILE with mode 600 and NEVER echoed.
#   - Only non-secret values reach stdout: key NAMES, HTTP status codes,
#     pipeline_run_id, counts, scan statuses.
#   - `set -x` is never enabled; no command that touches a secret is traced.
#
# Usage:
#   bloom-7_4b.sh inspect                 # what's in the profile (names only)
#   bloom-7_4b.sh token                   # mint JWT -> TOKEN_FILE (prints nothing secret)
#   bloom-7_4b.sh dispatch <id,id,id>     # POST /workflows/pipeline
#   bloom-7_4b.sh run <run_id>            # read back the run row
#   bloom-7_4b.sh scans <run_id>          # per-scan rows + counts

set -uo pipefail

PROFILE="${BLOOM_PROFILE:-pipeline-staging}"
CRED_FILE="$HOME/.bloom/credentials.${PROFILE}.txt"
# ⚠️ The :8443 is NOT optional. Staging and production share the host
# staging.bloom.salk.edu; without the port you land on PRODUCTION's Caddy and the TLS
# handshake still succeeds against prod's wildcard cert, so you silently dispatch against
# production. Confirmed in salk-bloom bloommcp/docs/connecting-claude-code.md:58-64.
#
# TWO DIFFERENT BASES, both on :8443 -- do not conflate them (measured 2026-09-17):
#   SERVER   = https://staging.bloom.salk.edu:8443        -> the workflows service
#              (/workflows/pipeline, /workflows/runs/{id})
#   SUPABASE = https://staging.bloom.salk.edu:8443/api    -> self-hosted Supabase behind Kong
#              (/auth/v1/token, /client-info); this is what BLOOM_API_URL in the
#              credentials profile holds, and what bloomctl passes to supabase.create_client.
# Proof they differ: an unauthenticated POST to /workflows/pipeline returns
#   {"detail":"Authorization Bearer token required"}   <- services/workflows/auth.py's own text
# while /api/workflows/pipeline returns {"message":"Unauthorized"} <- Kong's generic reply.
SERVER="${BLOOM_SERVER:-https://staging.bloom.salk.edu:8443}"
API="${BLOOM_API:-$SERVER}"
# The minted token is written OUTSIDE the repo, deliberately. An earlier draft of this
# script kept it next to itself; once the script lives in scripts/, that would drop a live
# credential into the working tree, one `git add -A` away from being committed.
TOKEN_FILE="${BLOOM_TOKEN_FILE:-$HOME/.bloom/.jwt-${PROFILE}}"

die() { echo "ERROR: $*" >&2; exit 1; }

[ -r "$CRED_FILE" ] || die "credentials file not readable: $CRED_FILE"

# Parse KEY=VALUE / KEY: VALUE, tolerant of either form. Values stay in vars only.
_get() {
  local key="$1"
  sed -nE "s/^[[:space:]]*${key}[[:space:]]*[:=][[:space:]]*(.*)$/\1/Ip" "$CRED_FILE" \
    | head -1 | tr -d '\r' | sed -E 's/^"(.*)"$/\1/'
}

cmd="${1:-inspect}"

case "$cmd" in
  inspect)
    echo "profile      : $PROFILE"
    echo "credentials  : $CRED_FILE"
    echo "api          : $API"
    echo "--- keys present (VALUES REDACTED) ---"
    sed -nE 's/^[[:space:]]*([A-Za-z_][A-Za-z0-9_]*)[[:space:]]*[:=].*$/  \1=<redacted>/p' "$CRED_FILE"
    echo "--- reachability (re-confirm; the routing was measured, not assumed) ---"
    # Expect 401 with auth.py's own wording. Anything else means the routing changed:
    # a 404 would mean /workflows is no longer proxied, and {"message":"Unauthorized"}
    # would mean this is hitting Kong -- i.e. the wrong base.
    body=$(curl -s --max-time 25 -X POST "$API/workflows/pipeline" \
             -H 'Content-Type: application/json' -d '{}' 2>/dev/null)
    code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 25 -X POST "$API/workflows/pipeline" \
             -H 'Content-Type: application/json' -d '{}' 2>/dev/null)
    printf '  POST %s -> HTTP %s\n' "$API/workflows/pipeline" "${code:-no-response}"
    printf '  body: %s\n' "$(printf '%s' "$body" | tr -d '\n' | head -c 120)"
    case "$body" in
      *"Authorization Bearer token required"*)
        echo "  OK: that is services/workflows/auth.py's own message -- right service." ;;
      *Unauthorized*)
        echo "  WRONG BASE: that is Kong. Do not put /api in front of /workflows." ;;
      *) echo "  UNEXPECTED: routing may have changed; stop and check before dispatching." ;;
    esac
    ;;

  token)
    # The profile holds BLOOM_API_URL (the Supabase base) plus BLOOM_EMAIL/BLOOM_PASSWORD.
    # api_url and anon_key can also be bootstrapped from the PUBLIC, unauthenticated
    # $SERVER/api/client-info endpoint -- the same path bloomctl's
    # auth.fetch_anon_credentials() uses -- so only the email/password are truly secret.
    SUPA_URL="$(_get 'BLOOM_API_URL')";       [ -n "$SUPA_URL" ]  || SUPA_URL="$(_get 'SUPABASE_URL')"
    SUPA_KEY="$(_get 'BLOOM_ANON_KEY')";      [ -n "$SUPA_KEY" ]  || SUPA_KEY="$(_get 'SUPABASE_ANON_KEY')"
    EMAIL="$(_get 'BLOOM_EMAIL')";            [ -n "$EMAIL" ]     || EMAIL="$(_get 'EMAIL')"
    PASSWORD="$(_get 'BLOOM_PASSWORD')";      [ -n "$PASSWORD" ]  || PASSWORD="$(_get 'PASSWORD')"
    if [ -z "$SUPA_URL" ] || [ -z "$SUPA_KEY" ]; then
      boot=$(curl -s --max-time 25 "$SERVER/api/client-info" 2>/dev/null)
      [ -n "$SUPA_URL" ] || SUPA_URL=$(printf '%s' "$boot" | python3 -c 'import json,sys
try: print(json.load(sys.stdin).get("api_url") or "")
except Exception: print("")')
      [ -n "$SUPA_KEY" ] || SUPA_KEY=$(printf '%s' "$boot" | python3 -c 'import json,sys
try: print(json.load(sys.stdin).get("anon_key") or "")
except Exception: print("")')
      echo "bootstrapped api_url/anon_key from $SERVER/api/client-info"
    fi
    [ -n "$SUPA_URL" ] || die "no Supabase api_url (profile BLOOM_API_URL, or /api/client-info)"
    [ -n "$SUPA_KEY" ] || die "no anon_key (profile, or /api/client-info)"
    [ -n "$EMAIL" ]    || die "no email key in profile"
    [ -n "$PASSWORD" ] || die "no password key in profile"

    resp=$(curl -s --max-time 30 "$SUPA_URL/auth/v1/token?grant_type=password" \
             -H "apikey: $SUPA_KEY" -H 'Content-Type: application/json' \
             --data-binary @<(printf '{"email":%s,"password":%s}' \
                 "$(printf '%s' "$EMAIL"    | python3 -c 'import json,sys;print(json.dumps(sys.stdin.read()))')" \
                 "$(printf '%s' "$PASSWORD" | python3 -c 'import json,sys;print(json.dumps(sys.stdin.read()))')"))
    tok=$(printf '%s' "$resp" | python3 -c 'import json,sys
try: print(json.load(sys.stdin).get("access_token") or "")
except Exception: print("")')
    if [ -z "$tok" ]; then
      printf '%s' "$resp" | python3 -c 'import json,sys
try:
  d=json.load(sys.stdin)
  print("auth failed:", d.get("error_description") or d.get("msg") or d.get("error") or list(d))
except Exception: print("auth failed: unparseable response")' >&2
      exit 1
    fi
    umask 077
    printf '%s' "$tok" > "$TOKEN_FILE"
    exp=$(printf '%s' "$tok" | cut -d. -f2 | tr '_-' '/+' | python3 -c '
import base64,json,sys,time
s=sys.stdin.read().strip(); s+="="*(-len(s)%4)
try:
  e=json.loads(base64.b64decode(s)).get("exp")
  print(int(e-time.time()) if e else "unknown")
except Exception: print("unknown")')
    echo "token minted -> $TOKEN_FILE (mode 600); expires in ${exp}s"
    ;;

  dispatch)
    ids="${2:?comma-separated scan_ids required}"
    [ -r "$TOKEN_FILE" ] || die "no token; run: $0 token"
    body=$(printf '%s' "$ids" | python3 -c '
import json,sys
ids=[int(x) for x in sys.stdin.read().strip().split(",") if x.strip()]
print(json.dumps({"target_level":"scan_ids","target_id":None,"scan_ids":ids}))')
    echo "POST $API/workflows/pipeline"
    echo "body: $body"
    out=$(curl -s --max-time 60 -w '\n%{http_code}' -X POST "$API/workflows/pipeline" \
            -H "Authorization: Bearer $(cat "$TOKEN_FILE")" \
            -H 'Content-Type: application/json' -d "$body")
    echo "HTTP $(printf '%s' "$out" | tail -1)"
    printf '%s' "$out" | sed '$d'
    echo
    ;;

  run)
    rid="${2:?run_id required}"
    [ -r "$TOKEN_FILE" ] || die "no token; run: $0 token"
    out=$(curl -s --max-time 30 -w '\n%{http_code}' "$API/workflows/runs/$rid" \
            -H "Authorization: Bearer $(cat "$TOKEN_FILE")")
    echo "HTTP $(printf '%s' "$out" | tail -1)"
    printf '%s' "$out" | sed '$d' | python3 -m json.tool 2>/dev/null \
      || printf '%s\n' "$(printf '%s' "$out" | sed '$d')"
    ;;

  scans)
    rid="${2:?run_id required}"
    [ -r "$TOKEN_FILE" ] || die "no token; run: $0 token"
    out=$(curl -s --max-time 30 "$API/workflows/runs/$rid" \
            -H "Authorization: Bearer $(cat "$TOKEN_FILE")")
    printf '%s' "$out" | python3 -c '
import json,sys
try: d=json.load(sys.stdin)
except Exception: print("unparseable"); raise SystemExit(1)
for k in ("id","status","scan_count","reused_count","done_count","failed_count",
          "argo_workflow_name","created_at","completed_at"):
    if k in d: print("%-20s %s" % (k, d[k]))
scans=d.get("scans") or d.get("run_scans") or []
if scans:
    print("\n--- per-scan ---")
    for s in scans:
        print("  %-12s %s" % (s.get("scan_id"), s.get("status")))
else:
    print("\n(no per-scan rows in this response; route may not embed them)")'
    ;;

  *) die "unknown subcommand: $cmd" ;;
esac
