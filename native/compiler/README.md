# Compiler for native benchmarks

The library and its unit tests work on published Fe master
`04d34410582e4ddac3f516c6ded1a0fdb4a31b3c`. The benchmark additionally needs
`std::native::black_box_u64`, implemented and tested in local Fe commit
`04a1c24b071086e6a171b21b2fe86d369d7b88d9`. That compiler commit has not been
published upstream; `native-black-box.patch` supplies the exact source change.

From a fresh Fe checkout at the recorded base, with Rust 1.98.1 and Node/npm:

```sh
git clone https://github.com/argotorg/fe fe-keccak-bench
cd fe-keccak-bench
git checkout 04d34410582e4ddac3f516c6ded1a0fdb4a31b3c
git apply /path/to/keccak/native/compiler/native-black-box.patch
npm ci --prefix crates/tree-sitter-fe
cargo +1.98.1 build --release --locked -p fe --features cranelift
```

Use `target/release/fe` with the standalone runner. Fe currently builds its
bundled documentation syntax highlighter through tree-sitter-fe, which requires
the pinned npm tree-sitter CLI. This is independent of Fe's language parser.

The repair adds a canonical standard-library declaration with a verified memory
contract, an opaque C runtime identity compiled separately with LTO disabled,
and automatic native executable/test linking. User extern declarations do not
inherit its trust. Regressions cover live borrows, host-I/O loops, edge scalar
values, user symbol collisions and retained optimized calls at O0/O1/O2. All
4,480 Fe workspace tests passed (one configured skip), as did nightly formatting
and all-target/all-feature Clippy. `manifest.json` records the exact identities
and checks. macOS execution has not been verified in this session.
