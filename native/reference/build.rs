use std::env;
use std::path::PathBuf;
use std::process::Command;

fn main() {
    let out = PathBuf::from(env::var_os("OUT_DIR").expect("Cargo output directory"));
    let object = out.join("barrier.o");
    let archive = out.join("libkeccak_barrier.a");
    assert!(
        Command::new("cc")
            .args(["-std=c11", "-O2", "-fno-lto", "-c", "../barrier.c", "-o"])
            .arg(&object)
            .status()
            .expect("compile benchmark barrier")
            .success()
    );
    assert!(
        Command::new("ar")
            .arg("rcs")
            .arg(&archive)
            .arg(&object)
            .status()
            .expect("archive benchmark barrier")
            .success()
    );
    println!("cargo:rerun-if-changed=../barrier.c");
    println!("cargo:rustc-link-search=native={}", out.display());
    println!("cargo:rustc-link-lib=static=keccak_barrier");
}
