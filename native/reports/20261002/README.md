# Native Keccak measurements, 2026-10-02

All four candidates passed the three library tests and 600 differential cases
per optimization level (O0/O1/O2), against both pinned Rust implementations.
The selected library is `8fc00ac`: 64-bit counters and fixed permutation lane
mapping. The eight-byte absorption experiment is retained as `lane-absorb.patch`
for reproduction; it was rejected because its gains were inconsistent.

## Alternating comparison

CPU nanoseconds per hash, median of 21 measured batches (three passes, seven
samples each). Implementations rotate order for every size and pass, on one
allowed Linux CPU. Each batch targets at least 50 ms of process CPU time, with
a minimum of 32 hashes. Input generation, allocation, I/O and startup are outside
the timer. Initialization, finalization, the opaque length call, and the rolling
checksum are inside it. The Fe column uses O2; Rust uses release optimization,
one codegen unit and no LTO. Both use the same C barrier.

| Bytes | Original | u64 counters | Fixed lanes (selected) | Eight-byte absorption | tiny-keccak | RustCrypto |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 76,429 | 7,986 | 499 | 451 | 269 | 304 |
| 32 | 78,337 | 10,015 | 803 | 852 | 250 | 264 |
| 136 | 138,488 | 21,037 | 1,499 | 1,549 | 508 | 497 |
| 4,096 | 2,507,312 | 336,496 | 41,227 | 30,230 | 8,889 | 8,058 |
| 65,536 | 39,488,781 | 4,800,906 | 515,844 | 550,895 | 143,873 | 133,258 |

These are measurements on a shared x86_64 Linux host, with compilation and other
work active. CPU affinity and CPU-time measurement do not eliminate frequency,
cache or scheduling effects; raw samples show that noise. The selected code is
about 61–153 times faster than the draft in this run, but remains slower than the
Rust references. Treat the magnitude and direction as evidence, not the last
digits as a stable performance guarantee. Eight-byte absorption improves the
4-KiB case while regressing several others, including 64 KiB.

The O2 executable text section shrank from 49,079 to 25,831 bytes with u64
counters, then to 23,103 bytes with fixed lanes. Eight-byte absorption raised it
to 23,815 bytes. These include the native protocol driver and are not standalone
library sizes. Fe `usize` is 256 bits even on the native target; `u64` is the
appropriate bounded loop-counter type here. Fixed lane mapping exposes the
constant rotations and array indices without unrolling all 24 rounds.

## Reproducing and provenance

`barrier-baseline.json`, `u64-indices.json`, `static-lanes.json` and
`lane-absorb.json` retain all checks, initial timing samples, source hashes,
compiler/executable hashes, build durations, package versions, CPU information
and flags. `alternating.json` contains the interleaved rerun above. No measurements
were discarded. `compare.py` reruns the comparison against the retained binaries
in the corresponding `native/out/*-20261002` directories, verifying their hashes
and digests. It must be run after those output directories are reproduced.

The baseline library is from `e7aad1b`, counters from `f185543`, and fixed lanes
from `8fc00ac`. The baseline's `native/support.py` differed by one trailing blank
line; its exact hash is recorded. The absorption patch applies to `8fc00ac`.
The measured compiler is a development build of Fe master `04d344105` with the
native scalar-barrier repair, identified by its SHA-256 in every report. Its
version string still names the base commit. The compiler patch and build
instructions under `native/compiler/` make that source change available; later
builds can differ in binary identity. Local absolute artifact paths in the JSON
are provenance, not portable input paths.
