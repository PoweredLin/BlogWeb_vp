"""V8-compatible SQLite storage. Never seed or replace an existing database."""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


def stamp():
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def dumps(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


class Store:
    def __init__(self, directory):
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        (self.directory / 'uploads').mkdir(exist_ok=True)
        self.path = self.directory / 'space.sqlite'

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('PRAGMA busy_timeout=5000')
        try:
            yield db
        finally:
            db.close()

    @contextmanager
    def transaction(self):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                yield db
                db.commit()
            except BaseException:
                db.rollback()
                raise

    def initialize(self):
        with self.connect() as db:
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version > 9:
                raise RuntimeError('Database is newer than this application; refusing downgrade')
            db.execute('PRAGMA journal_mode=WAL')
            existing = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='meta'").fetchone()
            if existing and version < 9:
                safety = self.directory / 'migration-safety'
                safety.mkdir(exist_ok=True)
                target = safety / 'before-v9.sqlite'
                if not target.exists():
                    with sqlite3.connect(target) as backup:
                        db.backup(backup)
            db.executescript('''
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS records(id TEXT PRIMARY KEY,kind TEXT NOT NULL,data TEXT NOT NULL,version INTEGER NOT NULL DEFAULT 1,created TEXT NOT NULL,updated TEXT NOT NULL,deleted TEXT,userId TEXT NOT NULL DEFAULT 'owner');
CREATE INDEX IF NOT EXISTS records_kind ON records(kind,deleted);
CREATE INDEX IF NOT EXISTS records_post_slug ON records(json_extract(data,'$.slug')) WHERE kind='posts' AND deleted IS NULL;
CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,expires INTEGER NOT NULL,userId TEXT NOT NULL DEFAULT 'owner');
CREATE TABLE IF NOT EXISTS tokens(id TEXT PRIMARY KEY,hash TEXT NOT NULL,name TEXT NOT NULL,expires INTEGER NOT NULL,created TEXT NOT NULL,userId TEXT NOT NULL DEFAULT 'owner');
CREATE TABLE IF NOT EXISTS ingest(token TEXT NOT NULL,key TEXT NOT NULL,hash TEXT NOT NULL,recordId TEXT NOT NULL,created TEXT NOT NULL,PRIMARY KEY(token,key));
CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY,event TEXT NOT NULL,recordId TEXT,created TEXT NOT NULL,userId TEXT NOT NULL DEFAULT 'owner');
CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,username TEXT UNIQUE NOT NULL,name TEXT NOT NULL,salt TEXT NOT NULL,hash TEXT NOT NULL,disabled INTEGER NOT NULL DEFAULT 0,created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS comments(id TEXT PRIMARY KEY,postId TEXT NOT NULL,name TEXT NOT NULL,content TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'pending',created TEXT NOT NULL,updated TEXT NOT NULL,version INTEGER NOT NULL DEFAULT 1);
CREATE INDEX IF NOT EXISTS comments_post ON comments(postId,status);
CREATE TABLE IF NOT EXISTS post_owners(postId TEXT PRIMARY KEY,userId TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS upload_owners(name TEXT PRIMARY KEY,userId TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS comment_rates(key TEXT PRIMARY KEY,count INTEGER NOT NULL,until INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS registrations(id TEXT PRIMARY KEY,username TEXT NOT NULL,name TEXT NOT NULL,salt TEXT NOT NULL,hash TEXT NOT NULL,reason TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'pending',created TEXT NOT NULL,reviewed TEXT);
CREATE UNIQUE INDEX IF NOT EXISTS registration_pending ON registrations(username) WHERE status='pending';
CREATE TABLE IF NOT EXISTS captchas(id TEXT PRIMARY KEY,answer TEXT NOT NULL,ip TEXT NOT NULL,expires INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS member_rates(key TEXT PRIMARY KEY,count INTEGER NOT NULL,expires INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS member_profiles(userId TEXT PRIMARY KEY,data TEXT NOT NULL,version INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS taxonomy(kind TEXT NOT NULL,name TEXT NOT NULL,PRIMARY KEY(kind,name));
CREATE TABLE IF NOT EXISTS journal(id TEXT PRIMARY KEY,kind TEXT NOT NULL,userId TEXT NOT NULL,data TEXT NOT NULL,version INTEGER NOT NULL DEFAULT 1,created TEXT NOT NULL,updated TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS journal_kind ON journal(kind);
CREATE TABLE IF NOT EXISTS git_cache(key TEXT PRIMARY KEY,data TEXT NOT NULL,etag TEXT,updated INTEGER NOT NULL DEFAULT 0,next_attempt INTEGER NOT NULL DEFAULT 0,lease_until INTEGER NOT NULL DEFAULT 0,error TEXT NOT NULL DEFAULT '');
''')
            for table in ('records', 'sessions', 'tokens', 'audit'):
                if 'userId' not in [r['name'] for r in db.execute(f'PRAGMA table_info({table})')]:
                    db.execute(f"ALTER TABLE {table} ADD COLUMN userId TEXT NOT NULL DEFAULT 'owner'")
            db.execute("UPDATE records SET userId=(SELECT userId FROM post_owners WHERE postId=records.id) WHERE kind='posts' AND id IN (SELECT postId FROM post_owners)")
            if not meta(db, 'taxonomyInitialized'):
                terms = {'categories': {'日常手记','技术笔记','作品随笔'}, 'tags': {'生活','开发','故事'}}
                for record in db.execute("SELECT data FROM records WHERE kind='posts'"):
                    p = json.loads(record['data'])
                    terms['categories'].add(p.get('category', ''))
                    terms['tags'].update(p.get('tags', '').replace('，', ',').split(','))
                for kind, names in terms.items():
                    for name in names:
                        if name.strip(): db.execute('INSERT OR IGNORE INTO taxonomy VALUES(?,?)', (kind,name.strip()))
                set_meta(db, 'taxonomyInitialized', True)
            db.execute('PRAGMA user_version=9')


def meta(db, key, default=None):
    r = db.execute('SELECT value FROM meta WHERE key=?', (key,)).fetchone()
    return json.loads(r['value']) if r else default


def set_meta(db, key, value):
    db.execute('INSERT INTO meta VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (key,dumps(value)))


def record(r):
    return {**json.loads(r['data']), **{k:r[k] for k in ('id','version','created','updated','deleted') if k in r.keys()}} if r else None


def audit(db, event, record_id='', user_id='owner'):
    db.execute('INSERT INTO audit(event,recordId,created,userId) VALUES(?,?,?,?)', (event,record_id,stamp(),user_id))
