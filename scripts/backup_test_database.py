"""Save a local PostgreSQL archive without displaying credentials or data."""
import datetime
import pathlib
import subprocess
import sys

root = pathlib.Path(__file__).resolve().parent.parent
backup_dir = root / 'backups'
backup_dir.mkdir(exist_ok=True)
stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
backup_path = backup_dir / f'omerofilestats-{stamp}.dump'
remote_command = (
    'pg_dump -w -U postgres -d "$POSTGRESQL_DATABASE" '
    '--format=custom --no-owner --no-acl'
)
with backup_path.open('xb') as output:
    result = subprocess.run(
        ['oc', '-n', 'core-omero-test', 'exec', 'deploy/filestatistics-pg15',
         '--', 'sh', '-c', remote_command],
        stdout=output, stderr=subprocess.PIPE, check=False,
    )
if result.returncode:
    print(f'Backup failed (exit {result.returncode}); incomplete file retained: {backup_path}', file=sys.stderr)
    print(result.stderr.decode(errors='replace')[-3000:], file=sys.stderr)
    sys.exit(result.returncode)
with backup_path.open('rb') as archive:
    if archive.read(5) != b'PGDMP':
        raise RuntimeError(f'Unexpected backup format: {backup_path}')
print(f'Created PostgreSQL custom-format archive: {backup_path} ({backup_path.stat().st_size} bytes)')
