"""Conservative, explicit setup of module-owned PostgreSQL baselines."""
from importlib.resources import files
import uuid

from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError, connections, transaction


def _normalize(value, schema):
    if value is None:
        return None
    return value.replace(f'"{schema}".', '').replace(f'{schema}.', '')


def _snapshot(cursor, schema, table_names):
    cursor.execute("""SELECT c.relname, c.relkind, c.relpersistence, c.relrowsecurity, c.relforcerowsecurity
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname=%s AND c.relkind IN ('r','p','i','S','v','m','f') ORDER BY c.relname""", [schema])
    objects = {row[0]: tuple(row[1:]) for row in cursor.fetchall()}
    cursor.execute("""SELECT c.relname, a.attname, pg_catalog.format_type(a.atttypid,a.atttypmod),
            a.attnotnull, a.attgenerated, a.attidentity, pg_get_expr(d.adbin,d.adrelid), a.attcollation::regcollation::text
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        JOIN pg_attribute a ON a.attrelid=c.oid
        LEFT JOIN pg_attrdef d ON d.adrelid=c.oid AND d.adnum=a.attnum
        WHERE n.nspname=%s AND c.relname=ANY(%s) AND a.attnum>0 AND NOT a.attisdropped
        ORDER BY c.relname,a.attname""", [schema, list(table_names)])
    columns = [tuple(_normalize(v, schema) if isinstance(v, str) else v for v in row) for row in cursor.fetchall()]
    cursor.execute("""SELECT c.relname, con.contype, pg_get_constraintdef(con.oid)
        FROM pg_constraint con JOIN pg_class c ON c.oid=con.conrelid
        JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname=%s AND c.relname=ANY(%s) ORDER BY c.relname,con.contype,pg_get_constraintdef(con.oid)""", [schema, list(table_names)])
    constraints = sorted(tuple(_normalize(v, schema) for v in row) for row in cursor.fetchall())
    cursor.execute("""SELECT t.relname, pg_get_indexdef(i.indexrelid)
        FROM pg_index i JOIN pg_class t ON t.oid=i.indrelid JOIN pg_namespace n ON n.oid=t.relnamespace
        WHERE n.nspname=%s AND t.relname=ANY(%s) ORDER BY t.relname,pg_get_indexdef(i.indexrelid)""", [schema, list(table_names)])
    indexes = sorted(tuple(_normalize(v, schema) for v in row) for row in cursor.fetchall())
    cursor.execute("""SELECT c.relname, pg_get_triggerdef(t.oid)
        FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname=%s AND c.relname=ANY(%s) AND NOT t.tgisinternal ORDER BY c.relname,pg_get_triggerdef(t.oid)""", [schema, list(table_names)])
    triggers = sorted(tuple(_normalize(v, schema) for v in row) for row in cursor.fetchall())
    cursor.execute("""SELECT c.relname, s.seqstart, s.seqincrement, s.seqmax, s.seqmin, s.seqcache, s.seqcycle
        FROM pg_sequence s JOIN pg_class c ON c.oid=s.seqrelid JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname=%s ORDER BY c.relname""", [schema])
    sequences = {row[0]: tuple(row[1:]) for row in cursor.fetchall()}
    return objects, columns, constraints, indexes, triggers, sequences


class SchemaSetupCommand(BaseCommand):
    package = ''
    tables = ()

    def add_arguments(self, parser):
        parser.add_argument('--database', default='default')
        parser.add_argument('--apply', action='store_true', help='Create the baseline if no conflicting objects exist.')

    def handle(self, *args, **options):
        alias = options['database']
        db = connections[alias]
        if db.vendor != 'postgresql':
            raise CommandError('Schema setup requires PostgreSQL.')
        sql = files(self.package).joinpath('schema', 'baseline.sql').read_text(encoding='utf-8')
        reference = 'dashboard_check_' + uuid.uuid4().hex
        quoted = db.ops.quote_name(reference)
        try:
            with transaction.atomic(using=alias):
                with db.cursor() as cursor:
                    cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended('cci-dashboard-schema-setup', 0))")
                    cursor.execute(f'CREATE SCHEMA {quoted}')
                    cursor.execute(sql.replace('public.', f'{quoted}.'))
                    expected = _snapshot(cursor, reference, self.tables)
                    actual = _snapshot(cursor, 'public', self.tables)
                    actual = (*actual[:-1], {name: actual[-1].get(name) for name in expected[-1]})
                    collisions = sorted(set(expected[0]) & set(actual[0]))
                    if collisions:
                        if any(actual[0].get(name) != kind for name, kind in expected[0].items()) or actual[1:] != expected[1:]:
                            raise CommandError('Existing objects collide with the module baseline or have an incompatible schema: ' + ', '.join(collisions))
                        outcome = 'Existing schema matches the baseline; no changes made.'
                    elif options['apply']:
                        cursor.execute(sql)
                        outcome = 'Created the module schema.'
                    else:
                        outcome = 'No collisions found; rerun with --apply to create the schema.'
                    cursor.execute(f'DROP SCHEMA {quoted} CASCADE')
        except DatabaseError as exc:
            raise CommandError('Schema setup failed; no changes were committed. Check database permissions and object collisions.') from exc
        self.stdout.write(self.style.SUCCESS(outcome))
