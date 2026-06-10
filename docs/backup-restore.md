# Backup & Restore

## Overview

Filmoteka stores all data in PostgreSQL. Backup and restore are available
via the admin UI and API. The backup directory (`/backups` by default) must
be mounted as a Docker volume when running in containers.

## Backup

### Via API (admin-only)

```http
POST /admin/backup
Authorization: Bearer <token>
```

Returns `202 Accepted` with a `job_id`. Poll `GET /admin/jobs/{job_id}`
until `status` is `completed`. The result contains the file path and size:

```json
{
  "job_id": 42,
  "status": "pending",
  "type": "backup"
}
```

### Via CLI (inside Docker)

```bash
docker exec filmoteka-api-1 pg_dump \
  -h db -U filmoteka -d filmoteka \
  --no-owner --no-acl \
  > /backups/filmoteka_$(date +%Y%m%d_%H%M%S).sql
```

### Output

Backup files are saved to `BACKUP_DIR` (`/backups` by default) as
`filmoteka_YYYYMMDD_HHMMSS.sql`. Each file is a plain SQL dump suitable for
`psql` restore.

## List Backups

```http
GET /admin/backups
Authorization: Bearer <token>
```

Returns a sorted list (newest first) of `.sql` files in the backup
directory:

```json
{
  "items": [
    {"filename": "filmoteka_20260610_120000.sql", "size_bytes": 1048576}
  ],
  "total": 1
}
```

## Restore

### Via API (admin-only)

```http
POST /admin/restore/filmoteka_20260610_120000.sql
Authorization: Bearer <token>
```

Returns `202 Accepted` with a `job_id`. Poll until completed.

**Warning:** Restore drops all existing data and recreates it from the
backup. Any changes made after the backup was created will be lost.

### Via CLI (inside Docker)

```bash
docker exec -i filmoteka-api-1 psql -h db -U filmoteka -d filmoteka \
  < /backups/filmoteka_20260610_120000.sql
```

## Configuration

| Setting | Env var | Default | Description |
|---|---|---|---|
| `backup_dir` | `BACKUP_DIR` | `/backups` | Directory for SQL dump files |

When running under Docker Compose, add a volume mount:

```yaml
services:
  api:
    volumes:
      - ./backups:/backups
```

## Testing

```bash
# Create a backup
curl -X POST http://localhost:8000/admin/backup \
  -H "Authorization: Bearer $(admin_token)"

# List backups
curl http://localhost:8000/admin/backups \
  -H "Authorization: Bearer $(admin_token)"

# Restore
curl -X POST http://localhost:8000/admin/restore/filmoteka_20260610_120000.sql \
  -H "Authorization: Bearer $(admin_token)"
```
