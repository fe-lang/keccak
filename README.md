# Keccak-256 in Fe

Allocation-free, streaming Ethereum Keccak-256 for native Fe programs. The
state is 25 64-bit lanes; inputs are borrowed and never retained or modified.
This implements Keccak padding (suffix `0x01`), not SHA3-256 (`0x06`).

```fe
use keccak::{Keccak256, keccak256, keccak256_word}

let digest = keccak256([97 as u8, 98, 99])
var state = Keccak256::new()
state.update([97 as u8, 98, 99], offset: 0, len: 2)
state.update([97 as u8, 98, 99], offset: 2, len: 1)
let streamed = state.finish()
var words = Keccak256::new()
words.update_word(0xff, len: 1)
words.update_word(sender, len: 20)
words.update_word(salt, len: 32)
let create2 = words.finish_word()
let word = keccak256_word([97 as u8, 98, 99])
```

`ByteSource` supplies `len()`, `byte_at(index)` and `lane_at(index)`, indexed
by `usize`, for arrays, `core::MemBuffer` and `core::MemSpan`. `lane_at` returns eight bytes as
a little-endian `u64`; it defaults to eight `byte_at` reads, and the buffer and
span read the lane at once. Implement them for other borrowed byte sources.
`update` checks its source range, accepts empty updates, and supports arbitrary
chunk boundaries; between lane boundaries it absorbs whole lanes.
`update_word(value, len)` absorbs the last `len` (at most 32) bytes of a word's
big-endian encoding, so a hash input built from words, addresses and single
bytes needs no buffer. `finish`
consumes the hash state and returns `[u8; 32]`; `finish_word` returns the digest
as a big-endian `u256`, as the EVM's `KECCAK256` does, and `keccak256_word`
hashes a whole source that way.

The permutation follows the [Keccak team specification](https://keccak.team/keccak_specs_summary.html).
The original library and benchmark foundation were developed in
[FeVM](https://github.com/fe-lang/fevm); this repository owns the implementation
and its tests.

## Tests

All five library tests pass at O0/O1/O2 natively and on EVM on Linux x86_64
with Fe master `3587ff999`, built with `--features cranelift`.
The library uses MVS `var` mutable values and `var own self` receivers.
Run the library's native tests at all optimization levels:

```sh
fe test . --backend native -O 0
fe test . --backend native -O 1
fe test . --backend native -O 2
```

Coverage includes fixed known answers, empty input, chunking across the
136-byte rate boundary, buffer and span lanes at every alignment against byte
reads, words of 0 to 32 bytes at every lane alignment against their bytes, the
word digest, and borrowed buffer subranges. The library tests also
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
