"""SQLite leased work queue. Each connection belongs to one worker operation."""
import json
from pathlib import Path
import sqlite3
import time
import uuid
from contextlib import contextmanager
from .ir import canonical, digest


class Store:
    def __init__(self, path):
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('''CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, payload TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'pending',
                owner TEXT, lease REAL, attempts INTEGER NOT NULL DEFAULT 0,
                report TEXT, artifact TEXT, updated REAL NOT NULL)''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def add(self, payload):
        identity = digest(payload)
        with self.connect() as db:
            db.execute('INSERT OR IGNORE INTO jobs(id,payload,updated) VALUES(?,?,?)', (identity, canonical(payload), time.time()))
        return identity

    def claim(self, lease_seconds=1800, max_attempts=3):
        now, owner = time.time(), uuid.uuid4().hex
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            # Exhausted crashed workers become visible terminal infrastructure failures.
            db.execute("UPDATE jobs SET state='done', report=?, updated=? WHERE state='running' AND lease<? AND attempts>=?",
                       (json.dumps({'status':'INFRASTRUCTURE_ERROR','reason':'worker retry budget exhausted'}), now, now, max_attempts))
            row = db.execute("SELECT * FROM jobs WHERE (state='pending' OR (state='running' AND lease<?)) AND attempts<? ORDER BY id LIMIT 1", (now, max_attempts)).fetchone()
            if not row: return None
            db.execute("UPDATE jobs SET state='running',owner=?,lease=?,attempts=attempts+1,updated=? WHERE id=?", (owner, now+lease_seconds, now, row['id']))
            return {'id': row['id'], 'owner': owner, 'payload': json.loads(row['payload'])}

    def heartbeat(self, job, seconds=1800):
        with self.connect() as db:
            return db.execute("UPDATE jobs SET lease=?,updated=? WHERE id=? AND owner=? AND state='running'", (time.time()+seconds, time.time(), job['id'], job['owner'])).rowcount == 1

    def finish(self, job, report, artifact):
        with self.connect() as db:
            return db.execute("UPDATE jobs SET state='done',report=?,artifact=?,updated=? WHERE id=? AND owner=? AND state='running'",
                              (json.dumps(report), str(artifact), time.time(), job['id'], job['owner'])).rowcount == 1

    def rows(self):
        with self.connect() as db:
            rows = [dict(row) for row in db.execute('SELECT * FROM jobs ORDER BY id')]
        for row in rows:
            row['payload'] = json.loads(row['payload'])
            row['report'] = json.loads(row['report']) if row['report'] else None
        return rows
