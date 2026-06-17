#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# V2 Acceptance — run against a running Filmoteka stack
# Usage:
#   bash scripts/run-acceptance.sh [http://localhost:8000]
#
# Requires: curl, jq
# Defaults to http://localhost:8000 if no argument given
# ---------------------------------------------------------------------------
set -euo pipefail

BASE="${1:-http://localhost:8000}"
ADMIN_USER="${ADMIN_USER:-mrsalt3000}"
ADMIN_PASS="${ADMIN_PASS:-dev}"
PASS=0
FAIL=0
WARN=0

ok()   { echo "  ✅ $1"; ((PASS++)); }
warn() { echo "  ⚠️  $1"; ((WARN++)); }
fail() { echo "  ❌ $1"; ((FAIL++)); }

echo "=== V2 Acceptance — $BASE ==="
echo ""

# ── Auth ──────────────────────────────────────────────────────────────────
echo "--- Auth ---"
TOKEN=$(curl -s "$BASE/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"username\":\"$ADMIN_USER\",\"password\":\"$ADMIN_PASS\"}" \
  | jq -r '.access_token // empty')

if [ -n "$TOKEN" ]; then
  ok "Admin login"
else
  fail "Admin login"
fi

API() { curl -s "$BASE$1" -H "Authorization: Bearer $TOKEN" ${2:+-H "Content-Type: application/json"} ${3:+-d "$3"}; }

# ── 1. Health ─────────────────────────────────────────────────────────────
echo "--- 1. Health ---"
HEALTH=$(curl -s "$BASE/health")
if echo "$HEALTH" | jq -e '.status == "ok"' > /dev/null 2>&1; then
  ok "Health: $(echo "$HEALTH" | jq -r '.status')"
else
  fail "Health: $(echo "$HEALTH" | jq -r '.status // "unknown"')"
fi

# ── 2. Catalog ────────────────────────────────────────────────────────────
echo "--- 2. Catalog ---"
FILMS=$(curl -s "$BASE/films?limit=5")
TOTAL=$(echo "$FILMS" | jq -r '.total // 0')
if [ "$TOTAL" -gt 0 ]; then
  ok "Catalog: $TOTAL films listed"
else
  warn "Catalog is empty (may need import)"
fi

# ── 3. FTS Search ─────────────────────────────────────────────────────────
echo "--- 3. FTS Search ---"
SEARCH=$(curl -s "$BASE/films?q=test&limit=3")
STOTAL=$(echo "$SEARCH" | jq -r '.total // 0')
echo "  FTS search 'test' → $STOTAL results"
if echo "$SEARCH" | jq -e '.items | length > 0' > /dev/null 2>&1; then
  ok "FTS search returned results"
else
  warn "FTS search returned 0 results (expected if no films match)"
fi

# ── 4. Series (if any) ────────────────────────────────────────────────────
echo "--- 4. Series ---"
SERIES=$(curl -s "$BASE/series")
STOTAL=$(echo "$SERIES" | jq -r '.total // 0')
echo "  Series count: $STOTAL"

# ── 5. Import scan ────────────────────────────────────────────────────────
echo "--- 5. Import scan ---"
SCAN=$(API "/admin/import/scan" POST)
SJOB=$(echo "$SCAN" | jq -r '.job_id // "none"')
if [ "$SJOB" != "none" ]; then
  ok "Import scan started (job $SJOB)"
else
  warn "Import scan: $(echo "$SCAN" | jq -r '.error // "unknown error"')"
fi

# ── 6. Posters ────────────────────────────────────────────────────────────
echo "--- 6. Posters ---"
POSTER=$(API "/admin/posters/fill-missing" POST)
PJOB=$(echo "$POSTER" | jq -r '.job_id // "none"')
if [ "$PJOB" != "none" ]; then
  ok "Poster fill-missing started (job $PJOB)"
else
  warn "Poster fill-missing: $(echo "$POSTER" | jq -r '.error // "unknown"')"
fi

# ── 7. Aliases ────────────────────────────────────────────────────────────
echo "--- 7. Aliases ---"
ALIAS=$(API "/admin/aliases/generate" POST)
AJOB=$(echo "$ALIAS" | jq -r '.job_id // "none"')
if [ "$AJOB" != "none" ]; then
  ok "Alias generation started (job $AJOB)"
elif echo "$ALIAS" | jq -e '.status == "error"' > /dev/null 2>&1; then
  warn "Alias generation skipped: $(echo "$ALIAS" | jq -r '.error')"
else
  warn "Alias: unexpected response: $(echo "$ALIAS" | jq -c '.')"
fi

# ── 8. DeepSeek enrichment ────────────────────────────────────────────────
echo "--- 8. DeepSeek enrichment ---"
ENRICH=$(API "/admin/enrich/deepseek" POST)
EJOB=$(echo "$ENRICH" | jq -r '.job_id // "none"')
if [ "$EJOB" != "none" ]; then
  ok "DeepSeek enrich started (job $EJOB)"
elif echo "$ENRICH" | jq -e '.status == "error"' > /dev/null 2>&1; then
  warn "DeepSeek enrich skipped: $(echo "$ENRICH" | jq -r '.error')"
else
  warn "Enrich: unexpected response: $(echo "$ENRICH" | jq -c '.')"
fi

# ── 9. Jobs ───────────────────────────────────────────────────────────────
echo "--- 9. Jobs ---"
JOBS=$(API "/admin/jobs")
JTOTAL=$(echo "$JOBS" | jq -r '.total // 0')
echo "  Active / recent jobs: $JTOTAL"

# ── 10. Active jobs progress endpoints ────────────────────────────────────
echo "--- 10. Progress endpoints ---"
for ep in poster-progress/1 alias-progress/1 enrich-progress/1; do
  CODE=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/admin/$ep" \
    -H "Authorization: Bearer $TOKEN")
  if [ "$CODE" = "200" ]; then
    ok "$ep → 200"
  else
    warn "$ep → $CODE (expected if no active job)"
  fi
done

# ── 11. Backup ────────────────────────────────────────────────────────────
echo "--- 11. Backup ---"
BACKUP=$(API "/admin/backup" POST)
BKJOB=$(echo "$BACKUP" | jq -r '.job_id // "none"')
if [ "$BKJOB" != "none" ]; then
  # Check if job succeeded
  sleep 2
  BKSTAT=$(API "/admin/jobs/$BKJOB")
  BKRES=$(echo "$BKSTAT" | jq -r '.status // "unknown"')
  if [ "$BKRES" = "completed" ]; then
    ok "Backup completed"
  else
    warn "Backup status: $BKRES"
  fi
else
  warn "Backup: $(echo "$BACKUP" | jq -r '.error // "unknown"')"
fi

# ── 12. Watch Stats ───────────────────────────────────────────────────────
echo "--- 12. Watch stats ---"
STATS=$(API "/admin/watch-stats")
echo "  Watch stats: $(echo "$STATS" | jq -c '.')" || echo "  Watch stats: error"

# ── Summary ───────────────────────────────────────────────────────────────
echo ""
echo "=== Summary ==="
echo "  ✅ Pass:  $PASS"
echo "  ⚠️  Warn:  $WARN"
echo "  ❌ Fail:  $FAIL"
echo ""
if [ "$FAIL" -gt 0 ]; then
  echo "Some checks failed — review output above."
  exit 1
elif [ "$WARN" -gt 0 ] && [ "$FAIL" -eq 0 ]; then
  echo "All critical checks pass. Warnings are expected for missing config."
fi
