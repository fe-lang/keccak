# Keccak-256 in Fe

Allocation-free, streaming Ethereum Keccak-256 for native Fe programs. The
state is 25 64-bit lanes; inputs are borrowed and never retained or modified.
This implements Keccak padding (suffix `0x01`), not SHA3-256 (`0x06`).

```fe
use keccak::{Keccak256, keccak256}

let digest = keccak256([97 as u8, 98, 99])
var state = Keccak256::new()
state.update([97 as u8, 98, 99], offset: 0, len: 2)
state.update([97 as u8, 98, 99], offset: 2, len: 1)
let streamed = state.finish()
```

`ByteSource` supplies `len()` and `byte_at(index)` for arrays, `core::MemBuffer`
and `core::MemSpan`. Implement it for other borrowed byte sources.
`update` checks its source range, accepts empty updates, and supports arbitrary
chunk boundaries. `finish` consumes the hash state and returns `[u8; 32]`.

The permutation follows the [Keccak team specification](https://keccak.team/keccak_specs_summary.html).
The original library and benchmark foundation were developed in
[FeVM](https://github.com/fe-lang/fevm); this repository owns the implementation
and its tests.

## Tests

All three library tests pass at O0/O1/O2 natively and on EVM on Linux x86_64
with Fe `0f2218d38` (branch `feat/owned-value-destruction`), built with
`--features cranelift`.
The library uses MVS `var` mutable values and `var own self` receivers.
Run the library's native tests at all optimization levels:

```sh
fe test . --backend native -O 0
fe test . --backend native -O 1
fe test . --backend native -O 2
```

Coverage includes fixed known answers, empty input, chunking across the
136-byte rate boundary, and borrowed buffer subranges. The library tests also
pass on EVM (`fe test .`).

## Native differential checks and benchmarks

`native/` owns the binary driver, two pinned Rust oracles (`tiny-keccak` 2.0.2
and RustCrypto `sha3` 0.10.9), and the Python runner. The complete runner needs
Fe's `std::native::black_box_u64` API in addition to native compilation support.
Until that API is upstream, build the [included compiler patch](native/compiler/README.md)
on the recorded published Fe base. The library itself does not need the patch.

```sh
python3 -m unittest discover -s native -p 'test_*.py'
cargo nextest r --release --no-fail-fast --manifest-path native/reference/Cargo.toml
python3 native/run.py --fe /path/to/fe --out native/out/checks --check-only
python3 native/run.py --fe /path/to/fe --out native/out/timing
```

Install Rust 1.98.1 through rustup, Python 3.10+, and a C compiler with binutils
(`size`/`objdump` on Linux, `size`/`otool` on macOS). `--toolchain` selects the
Rust reference toolchain explicitly. Every run uses its own Cargo output path.
The runner supports x86_64 Linux and AArch64 macOS; only Linux has been verified.

The runner executes all library tests and 600 deterministic randomized/chunked
comparisons at O0/O1/O2. Timing excludes process startup, allocation, parsing,
and I/O. Each hash includes initialization/finalization, one opaque scalar
barrier call, and an observable rolling checksum. Rust uses the same C barrier
as the Fe native runtime, with C optimization at O2 and LTO disabled.

Reports retain source/compiler/executable hashes, compiler flags, Rust package
metadata, host/CPU-affinity details, all samples, build duration, executable
sizes, and disassembly. On Linux, timed processes use one allowed CPU. CPU time
still depends on frequency and competing workloads; use an idle host for stable
comparisons. `--check-only` skips timing while retaining correctness checks.

The [recorded optimization experiments](native/reports/20261002/README.md) include
all raw samples, correctness results and the rejected absorption candidate.
