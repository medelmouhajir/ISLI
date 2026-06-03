#!/usr/bin/env python3
"""ISLI ChromaDB Backup and Restore

Usage:
    python chromadb_backup.py backup  --data-dir /data/vectors --output /backups/chroma_$(date +%Y%m%d).tar.gz
    python chromadb_backup.py restore --archive /backups/chroma_20260511.tar.gz --data-dir /data/vectors
    python chromadb_backup.py backup  --data-dir /data/vectors --output /backups/chroma_$(date +%Y%m%d).tar.gz --verify
"""

import argparse
import hashlib
import shutil
import sys
import tarfile
from pathlib import Path


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def backup(data_dir: str, output: str, verify: bool = False) -> int:
    src = Path(data_dir)
    if not src.exists():
        print(f"[error] Data directory not found: {data_dir}")
        return 1
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(out, "w:gz") as tar:
        tar.add(src, arcname="chroma_data")
    checksum = _sha256_file(out)
    print(f"[backup] ChromaDB archived to {out}")
    print(f"[backup] SHA-256: {checksum}")

    # Write sidecar checksum file
    sidecar = out.with_suffix(out.suffix + ".sha256")
    sidecar.write_text(f"{checksum}  {out.name}\n")
    print(f"[backup] Checksum sidecar: {sidecar}")

    if verify:
        print("[backup] Verifying archive integrity...")
        re_checksum = _sha256_file(out)
        if re_checksum != checksum:
            print(f"[error] Integrity check failed! Expected {checksum}, got {re_checksum}")
            return 2
        print("[backup] Integrity verified.")
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

    # Verify checksum if sidecar exists
    sidecar = arc.with_suffix(arc.suffix + ".sha256")
    if sidecar.exists():
        stored_checksum = sidecar.read_text().strip().split()[0]
        actual_checksum = _sha256_file(arc)
        if actual_checksum == stored_checksum:
            print(f"[restore] Integrity verified (SHA-256: {actual_checksum})")
        else:
            print(f"[warning] Integrity mismatch! Stored: {stored_checksum}, Actual: {actual_checksum}")
            return 2
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="ChromaDB Backup/Restore")
    sub = parser.add_subparsers(dest="command")
    b = sub.add_parser("backup")
    b.add_argument("--data-dir", default="/data/vectors")
    b.add_argument("--output", required=True)
    b.add_argument("--verify", action="store_true", help="Re-verify checksum after creation")
    r = sub.add_parser("restore")
    r.add_argument("--archive", required=True)
    r.add_argument("--data-dir", default="/data/vectors")
    args = parser.parse_args()
    if args.command == "backup":
        return backup(args.data_dir, args.output, verify=args.verify)
    if args.command == "restore":
        return restore(args.archive, args.data_dir)
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
