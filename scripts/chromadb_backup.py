#!/usr/bin/env python3
"""ISLI ChromaDB Backup and Restore

Usage:
    python chromadb_backup.py backup  --data-dir /data/vectors --output /backups/chroma_$(date +%Y%m%d).tar.gz
    python chromadb_backup.py restore --archive /backups/chroma_20260511.tar.gz --data-dir /data/vectors
"""

import argparse
import shutil
import sys
import tarfile
from pathlib import Path


def backup(data_dir: str, output: str) -> int:
    src = Path(data_dir)
    if not src.exists():
        print(f"[error] Data directory not found: {data_dir}")
        return 1
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(out, "w:gz") as tar:
        tar.add(src, arcname="chroma_data")
    print(f"[backup] ChromaDB archived to {out}")
    return 0


def restore(archive: str, data_dir: str) -> int:
    arc = Path(archive)
    if not arc.exists():
        print(f"[error] Archive not found: {archive}")
        return 1
    dst = Path(data_dir)
    if dst.exists():
        backup_old = dst.with_suffix(".backup")
        shutil.move(str(dst), str(backup_old))
        print(f"[restore] Existing data moved to {backup_old}")
    dst.mkdir(parents=True, exist_ok=True)
    with tarfile.open(arc, "r:gz") as tar:
        tar.extractall(path=dst.parent)
    print(f"[restore] ChromaDB restored to {dst}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="ChromaDB Backup/Restore")
    sub = parser.add_subparsers(dest="command")
    b = sub.add_parser("backup")
    b.add_argument("--data-dir", default="/data/vectors")
    b.add_argument("--output", required=True)
    r = sub.add_parser("restore")
    r.add_argument("--archive", required=True)
    r.add_argument("--data-dir", default="/data/vectors")
    args = parser.parse_args()
    if args.command == "backup":
        return backup(args.data_dir, args.output)
    if args.command == "restore":
        return restore(args.archive, args.data_dir)
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
