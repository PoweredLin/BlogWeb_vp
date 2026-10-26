"""Offline account administration and complete database/upload backups."""
import argparse
import getpass
import os
import shutil
import sqlite3
from pathlib import Path
from .main import ROOT
from .storage import Store,meta,set_meta,stamp
from .security import credentials
from .validation import DEFAULT_PROFILE,DEFAULT_STORY


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('command',choices=['owner-init','owner-reset','backup','check'])
    parser.add_argument('--data-dir',default=os.getenv('DATA_DIR',str(ROOT/'data')))
    parser.add_argument('--destination')
    args=parser.parse_args(); store=Store(args.data_dir)
    if args.command=='backup':
        if not store.path.is_file(): parser.error('Database not found')
        if not args.destination: parser.error('--destination is required')
        dest=Path(args.destination).resolve()
        if dest.exists(): parser.error('Destination must be a new directory')
        dest.mkdir(parents=True)
        with store.connect() as db,sqlite3.connect(dest/'space.sqlite') as target: db.backup(target)
        shutil.copytree(store.directory/'uploads',dest/'uploads')
        (dest/'backup.txt').write_text('Lin Notebook full site backup\n'+stamp()+'\nStop writes during backup to keep uploads consistent.\n',encoding='utf-8')
        print('Full backup complete:',dest); return
    store.initialize()
    if args.command=='check':
        with store.connect() as db:
            result=db.execute('PRAGMA integrity_check').fetchone()[0]
            print('SQLite integrity:',result)
            if result!='ok': raise SystemExit(1)
        return
    with store.connect() as db: existing=meta(db,'account')
    if args.command=='owner-init' and existing: parser.error('Owner already exists; no changes made')
    if args.command=='owner-reset' and not existing: parser.error('Owner does not exist')
    name=existing['name'] if existing else input('Display name [Lin]: ').strip() or 'Lin'
    password=getpass.getpass('New password (10+ characters): ')
    if password!=getpass.getpass('Repeat password: '): parser.error('Passwords do not match')
    salt,hashed=credentials(password)
    with store.transaction() as db:
        set_meta(db,'account',{'name':name,'salt':salt,'hash':hashed})
        if not existing: set_meta(db,'profile',{**DEFAULT_PROFILE,'name':name}); set_meta(db,'story',DEFAULT_STORY)
        db.execute("DELETE FROM sessions WHERE userId='owner'")
    print('Owner saved. Username: admin. Existing content retained.')


if __name__=='__main__': main()
