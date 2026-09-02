"""SQLite development storage behind a small repository interface.

Persistence is optional: FleetServer works entirely in-memory unless a
Repository is supplied, so nothing about existing in-memory callers or
tests changes. Schema changes are applied through a linear, versioned
migration list tracked in `schema_migrations`; each entry runs once.
"""
from __future__ import annotations
import json,sqlite3
from pathlib import Path

MIGRATIONS = [
    "CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT (datetime('now')))",
    "CREATE TABLE vehicles (vehicle_id INTEGER PRIMARY KEY, data TEXT NOT NULL)",
    "CREATE TABLE missions (mission_id TEXT PRIMARY KEY, data TEXT NOT NULL)",
    "CREATE TABLE audit_log (idx INTEGER PRIMARY KEY, body TEXT NOT NULL, hash TEXT NOT NULL)",
    "CREATE TABLE server_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)",
]

class SqliteRepository:
    """Development-grade persistence. Not a production migration tool."""
    def __init__(self,path):
        self.path=Path(path);self.conn=sqlite3.connect(str(self.path),isolation_level=None)
        self.conn.execute("PRAGMA journal_mode=WAL");self.conn.execute("PRAGMA foreign_keys=ON")
        self._migrate()
    def _migrate(self):
        has_table=self.conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'").fetchone()
        current=self.conn.execute("SELECT COALESCE(MAX(version),0) FROM schema_migrations").fetchone()[0] if has_table else 0
        for version,statement in enumerate(MIGRATIONS,start=1):
            if version<=current:continue
            self.conn.execute(statement);self.conn.execute("INSERT INTO schema_migrations(version) VALUES (?)",(version,))
    def schema_version(self):return self.conn.execute("SELECT COALESCE(MAX(version),0) FROM schema_migrations").fetchone()[0]
    def save_vehicle(self,vehicle_id,data:dict):
        self.conn.execute("INSERT INTO vehicles(vehicle_id,data) VALUES (?,?) ON CONFLICT(vehicle_id) DO UPDATE SET data=excluded.data",(vehicle_id,json.dumps(data,sort_keys=True,default=str)))
    def save_mission(self,mission_id,data:dict):
        self.conn.execute("INSERT INTO missions(mission_id,data) VALUES (?,?) ON CONFLICT(mission_id) DO UPDATE SET data=excluded.data",(mission_id,json.dumps(data,sort_keys=True,default=str)))
    def append_audit(self,index,body,hash_):
        self.conn.execute("INSERT INTO audit_log(idx,body,hash) VALUES (?,?,?)",(index,body,hash_))
    def load_vehicles(self)->dict:
        return {row[0]:json.loads(row[1]) for row in self.conn.execute("SELECT vehicle_id,data FROM vehicles")}
    def load_missions(self)->dict:
        return {row[0]:json.loads(row[1]) for row in self.conn.execute("SELECT mission_id,data FROM missions")}
    def load_audit(self)->list:
        return [{"body":row[0],"hash":row[1]} for row in self.conn.execute("SELECT body,hash FROM audit_log ORDER BY idx")]
    def get_meta(self,key,default=None):
        row=self.conn.execute("SELECT value FROM server_meta WHERE key=?",(key,)).fetchone();return row[0] if row else default
    def set_meta(self,key,value):
        self.conn.execute("INSERT INTO server_meta(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(key,str(value)))
    def close(self):self.conn.close()
