import atexit
import contextlib
import json
import os
import sqlite3
import time


_CREATE_TABLES = """\
CREATE TABLE IF NOT EXISTS inclusions
    (id INTEGER PRIMARY KEY,
     includes TEXT);

CREATE TABLE IF NOT EXISTS objects
    (type TEXT,
     id TEXT,
     inclusion_id INTEGER,
     timestamp INTEGER,
     contents TEXT,
     CONSTRAINT objects_pkey PRIMARY KEY (type, id));
"""


class Cache:
    def __init__(self, db_path):
        self._db_path = db_path
        self._conn = None

        self._inclusions_to_id = None
        self._id_to_inclusions = None

    def _open(self):
        if self._conn is None:
            atexit.register(self.close)
            db_dir = os.path.dirname(self._db_path)
            if db_dir:
                os.makedirs(db_dir, exist_ok=True)
            self._conn = sqlite3.connect(self._db_path)
            with self._conn:
                self._conn.executescript(_CREATE_TABLES)
        return self._conn

    def close(self):
        if self._conn is not None:
            self._conn.rollback()
            self._conn.close()
            self._conn = None
        atexit.unregister(self.close)

    def _cursor(self):
        return contextlib.closing(self._open().cursor())

    @staticmethod
    def _inclusions_to_str(inclusions_iterable):
        inclusions = sorted(set(inclusions_iterable))
        if any(',' in x or '@' in x for x in inclusions):
            raise ValueError("inclusion fields may not contain ','")
        if not inclusions:
            # Ugly workaround.  I don't understand why the insert in
            # get_id_for_includes won't store an empty string for contents.
            return '@'
        return ','.join(inclusions)

    @staticmethod
    def _str_to_inclusions(inclusions_str):
        if inclusions_str == '@':
            return frozenset()
        return frozenset(inclusions_str.split(','))

    def _read_inclusions(self):
        with self._open() as conn:
            cur = conn.cursor()
            inclusions_to_id = {}
            id_to_inclusions = {}

            cur.execute('SELECT id, includes FROM inclusions')
            for inclusion_id, includes in cur:
                inclusions = self._str_to_inclusions(includes)
                inclusions_to_id[inclusions] = inclusion_id
                id_to_inclusions[inclusion_id] = inclusions

        self._inclusions_to_id = inclusions_to_id
        self._id_to_inclusions = id_to_inclusions

    def _ensure_inclusions(self):
        if self._inclusions_to_id is None:
            self._read_inclusions()

    def _get_inclusions_by_id(self, inclusion_id):
        self._ensure_inclusions()
        try:
            return self._id_to_inclusions[inclusion_id]
        except KeyError:
            self._read_inclusions()
        return self._id_to_inclusions[inclusion_id]

    def _get_id_for_includes(self, includes):
        inclusions = frozenset(includes)
        self._ensure_inclusions()
        try:
            return self._inclusions_to_id[inclusions]
        except KeyError:
            pass

        with self._open() as conn:
            res = conn.execute('INSERT INTO inclusions (includes) VALUES (?)',
                               (self._inclusions_to_str(includes),))
        self._read_inclusions()
        return self._inclusions_to_id[inclusions]

    def _inclusion_id_satisfies(self, inclusion_id, required):
        inclusions = self._get_inclusions_by_id(inclusion_id)
        return all(x in inclusions for x in required)

    def get(self, type_, id_, includes, after=None):
        with self._open() as conn:
            cur = conn.cursor()
            cur.execute(
                'SELECT inclusion_id, timestamp, contents'
                '    FROM objects'
                '    WHERE type=? and id=?',
                (type_, id_))
            row = cur.fetchone()

        if row is None:
            return None

        inclusion_id, timestamp, contents = row

        if not self._inclusion_id_satisfies(inclusion_id, includes):
            return None
        if after is not None and timestamp < after:
            return None
        return json.loads(contents)

    def put(self, type_, id_, includes, obj, timestamp=None):
        if timestamp is None:
            timestamp = int(time.time())
        inclusion_id = self._get_id_for_includes(includes)
        with self._open() as conn:
            conn.execute(
                'INSERT OR REPLACE INTO objects'
                '    (type, id, inclusion_id, timestamp, contents)'
                '    VALUES (?, ?, ?, ?, ?)',
                (type_, id_, inclusion_id, timestamp, json.dumps(obj)))
