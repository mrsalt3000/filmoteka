# Test: Backup & Restore

## Prerequisites

- Running Filmoteka service (`docker compose up`)
- Admin user (register + promote or use `mrsalt3000` / `dev`)
- `BACKUP_DIR` mounted / writable (default `/backups`)

## Scenario 1: Create backup

```bash
# 1. Get admin token
TOKEN=$(curl -s http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"mrsalt3000","password":"dev"}' | jq -r '.access_token')

# 2. Create backup
BACKUP=$(curl -s -X POST http://localhost:8000/admin/backup \
  -H "Authorization: Bearer $TOKEN")
echo "$BACKUP" | jq .
# → {"job_id": 1, "status": "pending", "type": "backup"}

JOB_ID=$(echo "$BACKUP" | jq -r '.job_id')

# 3. Poll until complete
for i in $(seq 1 10); do
  STATUS=$(curl -s http://localhost:8000/admin/jobs/$JOB_ID \
    -H "Authorization: Bearer $TOKEN")
  echo "$STATUS" | jq .
  STATE=$(echo "$STATUS" | jq -r '.status')
  if [ "$STATE" = "completed" ]; then break; fi
  if [ "$STATE" = "failed" ]; then echo "FAILED"; exit 1; fi
  sleep 2
done

# 4. Verify result contains file path
echo "$STATUS" | jq -r '.result.file'
# → /backups/filmoteka_20260610_120000.sql
```

**Expected result:** Backup file created, job completed, file path in result.

## Scenario 2: List backups

```bash
curl -s http://localhost:8000/admin/backups \
  -H "Authorization: Bearer $TOKEN" | jq .
# → {"items": [{"filename":"filmoteka_20260610_120000.sql",...}], "total": 1}
```

**Expected result:** At least one backup file listed.

## Scenario 3: Restore from backup

```bash
# Get the latest backup filename
FILENAME=$(curl -s http://localhost:8000/admin/backups \
  -H "Authorization: Bearer $TOKEN" | jq -r '.items[0].filename')

# Start restore
RESTORE=$(curl -s -X POST "http://localhost:8000/admin/restore/$FILENAME" \
  -H "Authorization: Bearer $TOKEN")
echo "$RESTORE" | jq .
# → {"job_id": 2, "status": "pending", "type": "restore"}

RESTORE_JOB_ID=$(echo "$RESTORE" | jq -r '.job_id')

# Poll
for i in $(seq 1 30); do
  STATUS=$(curl -s "http://localhost:8000/admin/jobs/$RESTORE_JOB_ID" \
    -H "Authorization: Bearer $TOKEN" | jq -r '.status')
  if [ "$STATUS" = "completed" ]; then echo "RESTORED"; break; fi
  if [ "$STATUS" = "failed" ]; then echo "FAILED"; exit 1; fi
  sleep 2
done
```

**Expected result:** Restore completes. Library data is available again.

## Scenario 4: Restore nonexistent file

```bash
curl -s -X POST http://localhost:8000/admin/restore/nonexistent.sql \
  -H "Authorization: Bearer $TOKEN" | jq .
# → {"detail": "Backup file 'nonexistent.sql' not found"}
```

**Expected result:** 404 with clear error message.

## Cleanup

```bash
# Delete backup file via shell (not available via API)
docker exec filmoteka-api-1 rm -f /backups/filmoteka_*.sql
```
