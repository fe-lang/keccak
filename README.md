# Keccak-256 in Fe

Allocation-free, streaming Ethereum Keccak-256 for native Fe programs. The
state is 25 64-bit lanes; inputs are borrowed and never retained or modified.
This implements Keccak padding (suffix `0x01`), not SHA3-256 (`0x06`).

```fe
use keccak::{Keccak256, keccak256}

let digest = keccak256([97 as u8, 98, 99])
let mut state = Keccak256::new()
state.update([97 as u8, 98, 99], offset: 0, len: 2)
state.update([97 as u8, 98, 99], offset: 2, len: 1)
let streamed = state.finish()
```

`ByteSource` supplies `len()` and `byte_at(index)` for arrays and
`std::native::ByteBuffer`. Implement it for other borrowed byte sources.
`update` checks its source range, accepts empty updates, and supports arbitrary
chunk boundaries. `finish` consumes the hash state and returns `[u8; 32]`.

The permutation follows the [Keccak team specification](https://keccak.team/keccak_specs_summary.html).
The original library and benchmark foundation were developed in
[FeVM](https://github.com/fe-lang/fevm); this repository owns the implementation
and its tests.

## Tests

Verified on Linux x86_64 with Fe master
`04d34410582e4ddac3f516c6ded1a0fdb4a31b3c`, built with `--features cranelift`.
Run the library's native tests at all optimization levels:

```sh
fe test . --backend native -O 0
fe test . --backend native -O 1
fe test . --backend native -O 2
```

Coverage includes fixed known answers, empty input, chunking across the
136-byte rate boundary, and borrowed native-buffer subranges. The library
is currently verified for native compilation.
