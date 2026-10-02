use std::env;
use std::error::Error;
use std::io::{self, BufWriter, Read, Write};
use std::os::raw::c_long;

use sha3::{Digest, Keccak256};
use tiny_keccak::{Hasher, Keccak};

unsafe extern "C" {
    fn clock() -> c_long;
    fn __fe_native_black_box_u64(value: u64) -> u64;
}

#[derive(Clone, Copy)]
enum Implementation {
    Tiny,
    RustCrypto,
}

// Keep the same call boundary as the Fe driver. The caller passes a length
// returned by the shared C barrier, preventing repeated hashes being hoisted.
#[inline(never)]
fn digest(input: &[u8], chunk: usize, implementation: Implementation) -> [u8; 32] {
    let mut output = [0; 32];
    match implementation {
        Implementation::Tiny => {
            let mut state = Keccak::v256();
            if chunk == 0 {
                state.update(input);
            } else {
                for part in input.chunks(chunk) {
                    state.update(part);
                }
            }
            state.finalize(&mut output);
        }
        Implementation::RustCrypto => {
            let mut state = Keccak256::new();
            if chunk == 0 {
                state.update(input);
            } else {
                for part in input.chunks(chunk) {
                    state.update(part);
                }
            }
            output.copy_from_slice(&state.finalize());
        }
    }
    output
}

fn number(input: &mut impl Read) -> io::Result<u64> {
    let mut bytes = [0; 8];
    input.read_exact(&mut bytes)?;
    Ok(u64::from_le_bytes(bytes))
}

fn main() -> Result<(), Box<dyn Error>> {
    let implementation = match env::args().nth(1).as_deref() {
        Some("tiny") => Implementation::Tiny,
        Some("rustcrypto") => Implementation::RustCrypto,
        _ => return Err("expected tiny or rustcrypto implementation".into()),
    };
    let mut input = io::stdin().lock();
    let mut output = BufWriter::new(io::stdout().lock());
    let mut marker = [0];
    while input.read(&mut marker)? != 0 {
        if marker[0] != 64 {
            return Err("invalid request marker".into());
        }
        let rounds = number(&mut input)?;
        let chunk = usize::try_from(number(&mut input)?)?;
        let len = usize::try_from(number(&mut input)?)?;
        if rounds == 0 || rounds > 1_000_000_000 || len > 64 * 1024 * 1024 {
            return Err("request exceeds benchmark bounds".into());
        }
        let mut data = vec![0; len];
        input.read_exact(&mut data)?;
        let mut result = [0; 32];
        let mut checksum = 0_u64;
        // The harness verifies clock_t width and CLOCKS_PER_SEC on each host.
        let started = unsafe { clock() };
        for iteration in 0..rounds {
            let length = usize::try_from(unsafe { __fe_native_black_box_u64(len as u64) })?;
            result = digest(&data[..length], chunk, implementation);
            let word = u64::from_le_bytes(result[..8].try_into()?);
            checksum = checksum.rotate_left(1) ^ word ^ iteration;
        }
        let ended = unsafe { clock() };
        if started < 0 || ended < started {
            return Err("invalid CPU clock result".into());
        }
        output.write_all(&u64::try_from(ended - started)?.to_le_bytes())?;
        output.write_all(&result)?;
        output.write_all(&checksum.to_le_bytes())?;
        output.flush()?;
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::{Implementation, digest};

    #[test]
    fn known_answers_and_both_rust_implementations_agree() {
        for (input, expected) in [
            (
                &b""[..],
                "c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470",
            ),
            (
                &b"abc"[..],
                "4e03657aea45a94fc7d47ba826c8d667c0d1e6e33a64a036ec44f58fa12d6c45",
            ),
        ] {
            for implementation in [Implementation::Tiny, Implementation::RustCrypto] {
                let actual: String = digest(input, 0, implementation)
                    .iter()
                    .map(|byte| format!("{byte:02x}"))
                    .collect();
                assert_eq!(actual, expected);
            }
        }
    }

    #[test]
    fn chunking_agrees_at_padding_and_multiple_rate_boundaries() {
        for len in [0, 1, 7, 8, 31, 32, 135, 136, 137, 271, 272, 273, 4096] {
            let input: Vec<u8> = (0..len).map(|index| (index * 17 + 3) as u8).collect();
            let expected = digest(&input, 0, Implementation::Tiny);
            for chunk in [0, 1, 7, 8, 135, 136, 137, 271, 272, 4096] {
                for implementation in [Implementation::Tiny, Implementation::RustCrypto] {
                    assert_eq!(digest(&input, chunk, implementation), expected);
                }
            }
        }
    }
}
