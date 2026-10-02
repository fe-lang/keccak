#!/usr/bin/env python3
"""Check standalone Fe Keccak against two Rust implementations and compare CPU time."""
import argparse
from datetime import datetime, timezone
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import platform
import random
import shutil
import statistics
import struct
import subprocess
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
from support import host_info

MASK = (1 << 64) - 1


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def command(args, log, **kwargs):
    with log.open('wb') as output:
        subprocess.run([str(arg) for arg in args], stdout=output, stderr=subprocess.STDOUT,
                       check=True, timeout=1800, **kwargs)


@lru_cache(maxsize=256)
def checksum(word, rounds):
    value = 0
    for iteration in range(rounds):
        value = ((value << 1) & MASK | value >> 63) ^ word ^ iteration
    return value


def execute(executable, requests, expected=None):
    payload = b''.join(b'@' + struct.pack('<QQQ', rounds, chunk, len(data)) + data
                       for data, rounds, chunk in requests)
    result = subprocess.run([str(arg) for arg in executable], input=payload,
                            capture_output=True, check=True, timeout=180)
    if result.stderr or len(result.stdout) != 48 * len(requests):
        raise AssertionError(f'invalid benchmark response from {executable}: {result.stderr!r}')
    rows = []
    for index, (data, rounds, chunk) in enumerate(requests):
        response = result.stdout[48 * index:48 * (index + 1)]
        ticks = int.from_bytes(response[:8], 'little')
        value = response[8:40]
        observed = int.from_bytes(response[40:], 'little')
        if observed != checksum(int.from_bytes(value[:8], 'little'), rounds):
            raise AssertionError('iteration checksum differs')
        if expected is not None and value != expected[index]:
            raise AssertionError(f'digest differs for length={len(data)}, chunk={chunk}, rounds={rounds}')
        rows.append((ticks, value))
    return rows


def vectors():
    rng = random.Random(0xFECCAC256)
    lengths = sorted(set([*range(0, 34), 63, 64, 65, 134, 135, 136, 137, 138,
                          270, 271, 272, 273, 407, 408, 409, 1024, 4096, 16384]))
    messages = [rng.randbytes(length) for length in lengths]
    messages += [rng.randbytes(rng.randrange(8193)) for _ in range(48)]
    return [(message, 1, chunk) for message in messages for chunk in [0, 1, 7, 135, 136, 137]]


def measure(executable, data, expected, frequency, samples, milliseconds):
    rounds = 32
    while True:
        ticks = execute(executable, [(data, rounds, 0)], [expected])[0][0]
        if ticks >= frequency * milliseconds / 1000 or rounds >= 1 << 24:
            break
        rounds *= 2
    if ticks == 0:
        raise RuntimeError('CPU clock resolution is insufficient')
    # Requests execute in one resident process; discard its first measured batch.
    measured = execute(executable, [(data, rounds, 0)] * (samples + 1), [expected] * (samples + 1))[1:]
    values = [ticks * 1e9 / frequency / rounds for ticks, value in measured]
    median = statistics.median(values)
    return {'bytes': len(data), 'rounds': rounds, 'cpu_ns_per_hash': values,
            'median_cpu_ns': median, 'min_cpu_ns': min(values), 'max_cpu_ns': max(values),
            'median_mib_per_second': len(data) * 1e9 / median / (1024 * 1024)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fe', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--toolchain', default='1.98.1', help='installed Rust toolchain for the reference')
    parser.add_argument('--levels', nargs='+', choices=['0', '1', '2'], default=['0', '1', '2'])
    parser.add_argument('--samples', type=int, default=9)
    parser.add_argument('--milliseconds', type=int, default=50)
    parser.add_argument('--cpu', type=int, help='Linux CPU to pin measurements to; defaults to the first allowed CPU')
    parser.add_argument('--check-only', action='store_true')
    args = parser.parse_args()
    if args.samples < 3 or args.milliseconds < 1:
        parser.error('need at least three samples and a positive batch duration')
    affinity = None
    if hasattr(os, 'sched_getaffinity'):
        allowed = sorted(os.sched_getaffinity(0))
        cpu = min(allowed) if args.cpu is None else args.cpu
        if cpu not in allowed:
            parser.error(f'CPU {cpu} is outside the allowed set {allowed}')
        affinity = {'allowed_cpus': allowed, 'measurement_cpu': cpu}
    elif args.cpu is not None:
        parser.error('--cpu requires Linux CPU affinity support')
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    compiler = args.fe.resolve()
    sources = sorted([*ROOT.glob('src/**/*.fe'), *HERE.glob('driver/**/*.fe'),
                      *HERE.glob('driver/fe.toml'), *HERE.glob('*.py'), HERE / 'barrier.c',
                      *HERE.glob('reference/src/*.rs'), HERE / 'reference/build.rs',
                      HERE / 'reference/Cargo.toml', HERE / 'reference/Cargo.lock',
                      ROOT / 'fe.toml'])
    hashes = {str(path.relative_to(ROOT)): digest(path) for path in sources}
    cargo = ['rustup', 'run', args.toolchain, 'cargo']
    rust_target = out / 'reference-target'
    rust_env = os.environ | {'CARGO_TARGET_DIR': str(rust_target)}
    record = {'schema': 1, 'complete': False, 'created': datetime.now(timezone.utc).isoformat(),
              'compiler_sha256': digest(compiler),
              'compiler_version': subprocess.check_output([compiler, '--version'], text=True).strip(),
              'rustc': subprocess.check_output(['rustup', 'run', args.toolchain, 'rustc', '-vV'], text=True),
              'cargo': subprocess.check_output([*cargo, '--version'], text=True).strip(),
              'rust_toolchain': args.toolchain, 'rust_target_directory': str(rust_target),
              'rust_flags': {'profile': 'release', 'lto': False, 'codegen_units': 1,
                             'RUSTFLAGS': os.environ.get('RUSTFLAGS', ''),
                             'CARGO_ENCODED_RUSTFLAGS': os.environ.get('CARGO_ENCODED_RUSTFLAGS', '')},
              'source_sha256': hashes, 'executables': {}, 'checks': {}, 'measurements': {},
              'timing_scope': 'resident hashing including state initialization/finalization, one opaque '
                              'length call and a rolling checksum per hash; input allocation, I/O, '
                              'process startup and parsing excluded'}
    report = out / 'results.json'

    def save():
        report.write_text(json.dumps(record, indent=2) + '\n')

    save()
    try:
        record['host'] = host_info(out)
        record['host']['affinity'] = affinity
        if affinity is not None:
            cpu_dir = Path(f'/sys/devices/system/cpu/cpu{affinity["measurement_cpu"]}')
            record['host']['cpu_settings'] = {
                name: (cpu_dir / name).read_text().strip()
                for name in ['cpufreq/scaling_governor', 'cpufreq/scaling_driver',
                             'cpufreq/scaling_min_freq', 'cpufreq/scaling_max_freq',
                             'topology/thread_siblings_list'] if (cpu_dir / name).exists()}
        started = time.perf_counter()
        command([*cargo, 'build', '--release', '--locked', '--target-dir', rust_target,
                 '--manifest-path', HERE / 'reference/Cargo.toml'],
                out / 'rust-build.log', env=rust_env)
        record['rust_build_seconds'] = time.perf_counter() - started
        metadata = subprocess.check_output([*cargo, 'metadata', '--locked', '--format-version', '1',
                                            '--manifest-path', HERE / 'reference/Cargo.toml'], text=True, env=rust_env)
        (out / 'rust-metadata.json').write_text(metadata)
        rust = out / 'rust-keccak'
        shutil.copy2(rust_target / 'release/keccak-reference', rust)
        executables = {'rust-tiny': [rust, 'tiny'], 'rustcrypto': [rust, 'rustcrypto']}
        for level in args.levels:
            folder = out / f'O{level}'
            folder.mkdir()
            command([compiler, 'test', ROOT, '--backend', 'native', '-O', level],
                    folder / 'tests.log')
            record['checks'][f'unit-O{level}'] = 'passed'
            save()
            started = time.perf_counter()
            command([compiler, 'build', HERE / 'driver', '--backend', 'native', '-O', level,
                     '--emit', 'ir,executable', '--out-dir', folder, '--report', '--report-out', folder / 'build.tar.gz'],
                    folder / 'build.log')
            executables[f'fe-O{level}'] = [folder / 'keccak_bench']
            record['executables'][f'fe-O{level}'] = {'build_seconds': time.perf_counter() - started}
        for name, executable in executables.items():
            record['executables'].setdefault(name, {}).update(
                sha256=digest(executable[0]), bytes=executable[0].stat().st_size)
            command(['size', executable[0]], out / f'{name}-size.txt')
            disassembler = ['otool', '-tvV'] if platform.system() == 'Darwin' else ['objdump', '-dr']
            command([*disassembler, executable[0]], out / f'{name}-assembly.txt')
        requests = vectors()
        expected = [value for ticks, value in execute(executables['rust-tiny'], requests)]
        for name, executable in executables.items():
            execute(executable, requests, expected)
            record['checks'][name] = len(requests)
            save()
        if not args.check_only:
            if affinity is not None:
                os.sched_setaffinity(0, {affinity['measurement_cpu']})
            for index, length in enumerate([0, 1, 32, 64, 135, 136, 137, 272, 1024, 4096, 16384, 65536]):
                data = random.Random(length).randbytes(length)
                expected = execute(executables['rust-tiny'], [(data, 1, 0)])[0][1]
                # Rotate implementation order by size to reduce fixed-order drift.
                entries = list(executables.items())
                rotation = index % len(entries)
                for name, executable in entries[rotation:] + entries[:rotation]:
                    row = measure(executable, data, expected, record['host']['clock_ticks_per_second'],
                                  args.samples, args.milliseconds)
                    record['measurements'].setdefault(name, []).append(row)
                    save()
        if hashes != {str(path.relative_to(ROOT)): digest(path) for path in sources}:
            raise RuntimeError('benchmark sources changed during the run')
        record['complete'] = True
    except Exception as error:
        record['error'] = str(error)
        raise
    finally:
        save()
    print(f'Keccak: {len(requests)} cases per implementation passed; see {report}')


if __name__ == '__main__':
    main()
