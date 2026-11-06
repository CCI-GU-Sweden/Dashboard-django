"""Read existing collector-owned upload data; no schema migrations or writes."""
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone

from django.db import connection


class InvalidUploadFilters(ValueError):
    pass


def upload_summary(params):
    try:
        period = int(params.get('period', '30'))
        if not 1 <= period <= 3650:
            raise ValueError
        start_text, end_text = params.get('startDate'), params.get('endDate')
        if bool(start_text) != bool(end_text):
            raise ValueError
        if start_text:
            start_date, end_date = date.fromisoformat(start_text), date.fromisoformat(end_text)
            if start_date > end_date:
                raise ValueError
            start = datetime.combine(start_date, time.min, tzinfo=timezone.utc)
            end = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=timezone.utc)
        else:
            end = datetime.now(timezone.utc)
            start = end - timedelta(days=period)
    except (ValueError, OverflowError):
        raise InvalidUploadFilters('Enter a valid period or date range.') from None

    scope = params.get('scope', 'all')
    if len(scope) > 200:
        raise InvalidUploadFilters('Invalid microscope.')
    sql = 'SELECT scope, time, username, file_count, total_file_size_mb, import_time_s FROM imports WHERE time >= %s AND time < %s'
    values = [start, end]
    if scope != 'all':
        sql += ' AND scope = %s'
        values.append(scope)
    with connection.cursor() as cursor:
        cursor.execute(sql, values)
        rows = cursor.fetchall()
    total_files, total_mb, total_seconds = 0, 0.0, 0.0
    users, scopes, months, days = set(), defaultdict(lambda: [0, 0.0]), set(), defaultdict(int)
    for microscope, timestamp, username, files, size_mb, seconds in rows:
        files, size_mb, seconds = int(files or 0), float(size_mb or 0), float(seconds or 0)
        if timestamp.tzinfo:
            timestamp = timestamp.astimezone(timezone.utc)
        day = timestamp.date().isoformat()
        months.add(day[:7])
        users.add(username)
        total_files += files
        total_mb += size_mb
        total_seconds += seconds
        scopes[microscope][0] += files
        scopes[microscope][1] += size_mb / 1024
        days[day] += files
    size_gb = total_mb / 1024
    top_files = max(scopes.items(), key=lambda item: item[1][0], default=None)
    top_size = max(scopes.items(), key=lambda item: item[1][1], default=None)
    peak = max(days.items(), key=lambda item: item[1], default=None)
    return {
        'total_files': total_files,
        'total_size_gb': round(size_gb, 2),
        'unique_users': len(users),
        'avg_import_size_gb': round(size_gb / len(rows), 2) if rows else 0,
        'avg_size_per_month_gb': round(size_gb / len(months), 2) if months else 0,
        'avg_time_per_gb': round(total_seconds / size_gb, 3) if size_gb else 0,
        'avg_files_per_month': round(total_files / len(months), 2) if months else 0,
        'top_scope_files': {'name': top_files[0], 'count': top_files[1][0]} if top_files else None,
        'top_scope_size': {'name': top_size[0], 'size_gb': round(top_size[1][1], 2)} if top_size else None,
        'peak_day': {'date': peak[0], 'count': peak[1]} if peak else None,
        'history': [{'date': day, 'count': count} for day, count in sorted(days.items())],
    }
