"""Portable download, resume and verification for the book's chapters 3/4/6."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
import csv
import gzip
import json
import os
from pathlib import Path
import re
import time
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent
CHAPTERS = {"3": "chapter_03_dna", "4": "chapter_04_graphs", "6": "chapter_06_localization"}
CHUNK = 32 * 1024 * 1024  # Required for compatibility with legacy range state.


def write_json(path, value):
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


@contextmanager
def exclusive(root):
    """OS lock is released on exit/crash; an old lock file is harmless."""
    with (root / ".download.lock").open("a+b") as handle:
        if os.fstat(handle.fileno()).st_size == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError("Another downloader/verifier is using this directory.") from exc
        try:
            yield
        finally:
            if os.name == "nt":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


def records_from(manifest, root, chapters):
    rows = json.loads(manifest.read_text(encoding="utf-8-sig"))
    results = []
    for row in rows:
        # Accept old absolute manifests after moving the whole directory.
        raw = row["path"].replace("\\", "/")
        match = re.search(r"(?:^|/)(chapter_0[346]_[^/]+/.+)$", raw)
        if not match:
            raise ValueError(f"Invalid dataset path: {raw}")
        relative = Path(match[1])
        if relative.parts[0] not in {CHAPTERS[c] for c in chapters}:
            continue
        destination = (root / relative).resolve()
        if not destination.is_relative_to(root):
            raise ValueError(f"Path escapes destination: {raw}")
        size = int(row["expected_bytes"])
        if size <= 0:
            raise ValueError(f"Invalid size: {raw}")
        results.append({**row, "path": relative.as_posix(), "expected_bytes": size})
    for chapter in chapters:
        if not any(r["path"].startswith(CHAPTERS[chapter] + "/") for r in results):
            raise ValueError(f"No files for chapter {chapter} in manifest")
    return results


def stream_range(url, path, start, end):
    headers = {"Accept-Encoding": "identity", "Range": f"bytes={start}-{end}"}
    with urlopen(Request(url, headers=headers), timeout=90) as response:
        expected = end - start + 1
        content_range = response.headers.get("Content-Range", "")
        if response.status == 206:
            if not content_range.startswith(f"bytes {start}-{end}/"):
                raise RuntimeError(f"Unexpected Content-Range: {content_range}")
        elif response.status != 200 or start != 0:
            raise RuntimeError("Server does not support the requested resume range")
        received = 0
        with path.open("r+b", buffering=0) as handle:
            handle.seek(start)
            while data := response.read(1024 * 1024):
                if received + len(data) > expected:
                    raise RuntimeError("Server returned more bytes than requested")
                handle.write(data)
                received += len(data)
            handle.flush()
            os.fsync(handle.fileno())
        if received != expected:
            raise RuntimeError(f"Incomplete response: {received}/{expected}")


def download(row, root, workers, retries):
    target = root / row["path"]
    size, url = row["expected_bytes"], row["url"]
    if target.exists():
        if target.stat().st_size != size:
            raise RuntimeError(f"Existing final file has incorrect size: {target}")
        print("SKIP", row["path"], flush=True)
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    state = target.with_name(target.name + ".ranges.json")
    part = target.with_name(target.name + ".parallel.part")
    old = target.with_name(target.name + ".part")
    if state.exists():
        saved = json.loads(state.read_text(encoding="utf-8-sig"))
        if not part.exists() or part.stat().st_size != size:
            raise RuntimeError(f"Resume data missing or wrong size: {part}")
        if saved.get("chunk_bytes", CHUNK) != CHUNK or saved.get("expected_bytes", size) != size:
            raise RuntimeError(f"Resume metadata does not match manifest: {state}")
        if saved.get("url", url) != url:
            raise RuntimeError(f"Resume URL differs: {state}")
        prefix, done = int(saved["prefix"]), set(saved["done"])
    else:
        if part.exists():
            raise RuntimeError(f"Range file without progress metadata: {part}")
        prefix, done = (old.stat().st_size if old.exists() else 0), set()
        if prefix > size:
            raise RuntimeError(f"Partial file exceeds expected size: {old}")
        if old.exists():
            old.rename(part)
        else:
            part.touch()
        # Preallocation is never treated as downloaded progress.
        with part.open("r+b") as handle:
            handle.truncate(size)
        write_json(state, {"prefix": prefix, "done": [], "expected_bytes": size,
                           "url": url, "chunk_bytes": CHUNK})
    if not 0 <= prefix <= size:
        raise RuntimeError(f"Invalid prefix in {state}")
    ranges = [(i, b, min(b + CHUNK, size) - 1) for i, b in enumerate(range(prefix, size, CHUNK))]
    if any(type(i) is not int or not 0 <= i < len(ranges) for i in done):
        raise RuntimeError(f"Invalid completed ranges in {state}")

    def fetch(item):
        i, begin, end = item
        for attempt in range(retries):
            try:
                stream_range(url, part, begin, end)
                return i
            except Exception:
                if attempt + 1 == retries:
                    raise
                time.sleep(min(30, 2 ** attempt))

    print("DOWNLOAD", row["path"], "bytes", size, "completed ranges", len(done), flush=True)
    last = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(fetch, item) for item in ranges if item[0] not in done]
        try:
            for future in as_completed(futures):
                done.add(future.result())
                write_json(state, {"prefix": prefix, "done": sorted(done), "expected_bytes": size,
                                   "url": url, "chunk_bytes": CHUNK})
                now = time.monotonic()
                if now - last >= 25:
                    completed = prefix + sum(e - b + 1 for i, b, e in ranges if i in done)
                    print(f"PROGRESS {row['path']} {completed}/{size} {completed / size:.2%}", flush=True)
                    last = now
        except BaseException:
            for future in futures:
                future.cancel()
            raise
    if len(done) != len(ranges) or part.stat().st_size != size:
        raise RuntimeError(f"Incomplete download: {target}")
    part.replace(target)
    print("DOWNLOADED", row["path"], flush=True)


def verify(rows, root, chapters):
    for row in rows:
        path = root / row["path"]
        if not path.is_file() or path.stat().st_size != row["expected_bytes"]:
            raise RuntimeError(f"Missing or incomplete: {path}")
    if "3" in chapters:
        total = 0
        for row in rows:
            if not row["path"].startswith(CHAPTERS["3"] + "/"):
                continue
            with (root / row["path"]).open(encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                if not {"sequence", "label"}.issubset(reader.fieldnames or []):
                    raise ValueError(f"Unexpected CSV columns: {row['path']}")
                for record in reader:
                    if len(record["sequence"]) != 200 or set(record["sequence"]) - set("ACGT") or record["label"] not in {"0", "1"}:
                        raise ValueError(f"Invalid sequence/label: {row['path']}, line {reader.line_num}")
                    total += 1
        print("DNA_OK", total, "rows", flush=True)
    if "4" in chapters:
        for row in rows:
            if row["path"].startswith(CHAPTERS["4"] + "/") and row["path"].endswith(".gz"):
                with gzip.open(root / row["path"], "rb") as handle:
                    while handle.read(1024 * 1024):
                        pass
        print("GRAPH_GZIP_OK", flush=True)
    if "6" in chapters:
        import numpy as np
        base = root / CHAPTERS["6"]
        labels = np.load(base / "labels.npy", allow_pickle=True)
        images = np.memmap(base / "images.npy", dtype="float32", mode="r").reshape(-1, 100, 100, 1)
        if labels.shape != (len(images), 7):
            raise ValueError(f"Image/label mismatch: {images.shape}, {labels.shape}")
        if not all(np.isfinite(images[i]).all() for i in (0, len(images) // 2, len(images) - 1)):
            raise ValueError("Non-finite image sample")
        print("LOCALIZATION_OK", images.shape, labels.shape, flush=True)
    print("VERIFIED", len(rows), "files", flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, default=HERE)
    parser.add_argument("--manifest", type=Path, default=HERE / "download_manifest.json")
    parser.add_argument("--chapters", nargs="+", choices=CHAPTERS, default=list(CHAPTERS))
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--retries", type=int, default=10)
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--download-only", action="store_true")
    args = parser.parse_args(argv)
    if args.workers < 1 or args.retries < 1:
        parser.error("workers and retries must be positive")
    if args.verify_only and args.download_only:
        parser.error("verify-only and download-only are mutually exclusive")
    if not args.download_only and "6" in args.chapters:
        try:
            import numpy  # Check before starting downloads; never install packages.
        except ImportError as exc:
            raise RuntimeError("NumPy is needed for chapter 6 verification. Use an environment that has it, or --download-only.") from exc
    root = args.destination.resolve()
    root.mkdir(parents=True, exist_ok=True)
    rows = records_from(args.manifest, root, args.chapters)
    with exclusive(root):
        complete = root / "COMPLETE.txt"
        if complete.exists():
            complete.unlink()
        if not args.verify_only:
            for row in sorted(rows, key=lambda r: r["expected_bytes"]):
                download(row, root, args.workers, args.retries)
        if not args.download_only:
            verify(rows, root, args.chapters)
            if set(args.chapters) == set(CHAPTERS):
                complete.write_text("ALL_DATASETS_DOWNLOADED_AND_VERIFIED\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
