"""Self-contained adapter checks; no cloud database or credentials are needed."""
import db_backend

class Field:
    def __init__(self, name): self.name = name

class FakeCursor:
    def __init__(self, rows=(), cols=('id',)):
        self.rows = list(rows)
        self.description = [Field(x) for x in cols]
    def fetchone(self):
        return self.rows.pop(0) if self.rows else None
    def fetchall(self):
        rows, self.rows = self.rows, []
        return rows
    def __iter__(self):
        yield from self.rows

class FakeDb:
    def __init__(self): self.statements = []
    def execute(self, sql, args=()):
        self.statements.append((sql, args))
        if 'RETURNING id' in sql: return FakeCursor([(18,)])
        return FakeCursor([('Han', 'tech')], ('full_name','role'))


def test_row_has_sqlite_compatible_access():
    r = db_backend.MixedRow([('id', 32), ('role', 'tech')])
    assert r['id'] == 32 and r[0] == 32 and dict(r)['role'] == 'tech'


def test_postgres_adapter_query_and_returning():
    fake = FakeDb()
    adapter = db_backend.PgConnection.__new__(db_backend.PgConnection)
    adapter.db = fake
    assert adapter.execute('INSERT INTO cards(card_code) VALUES(?)', ('ABC',)).lastrowid == 18
    assert fake.statements[-1] == ('INSERT INTO cards(card_code) VALUES(%s) RETURNING id', ('ABC',))
    result = adapter.execute('SELECT full_name,role FROM users WHERE username=? COLLATE NOCASE', ('ADMIN',))
    assert result.fetchone()['full_name'] == 'Han'
    assert 'LOWER(username)=LOWER(%s)' in fake.statements[-1][0]


def test_postgres_adapter_atomic_lock():
    fake = FakeDb()
    adapter = db_backend.PgConnection.__new__(db_backend.PgConnection)
    adapter.db = fake
    adapter.execute('BEGIN IMMEDIATE')
    assert 'pg_advisory_xact_lock' in fake.statements[-1][0]
