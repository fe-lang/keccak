"""Native benchmark host and CPU clock discovery (stdlib only)."""
from pathlib import Path
import platform
import subprocess


def command(args, **kwargs):
    result = subprocess.run([str(x) for x in args], capture_output=True, timeout=600, **kwargs)
    if result.returncode:
        raise RuntimeError(f'command failed ({result.returncode}): {args}\n'
                           + result.stdout.decode(errors='replace')
                           + result.stderr.decode(errors='replace'))
    return result.stdout



def host_info(out):
    system = (platform.system(), platform.machine())
    if system not in [('Darwin', 'arm64'), ('Linux', 'x86_64')]:
        raise RuntimeError(f'unsupported native acceptance host: {system}')
    # Verify the scalar libc clock ABI and conversion rather than assuming its rate.
    probe = out / 'clock_probe.c'
    probe.write_text('#include <stdio.h>\n#include <time.h>\n'
                     'int main(void) { printf("%zu %lld\\n", sizeof(clock_t), '
                     '(long long)CLOCKS_PER_SEC); return 0; }\n')
    binary = out / 'clock_probe'
    command(['cc', '-O2', probe, '-o', binary])
    width, frequency = map(int, command([binary]).split())
    if width != 8 or frequency <= 0:
        raise RuntimeError(f'unsupported clock_t ABI: {width} bytes / {frequency} Hz')
    return {'system': system[0], 'machine': system[1], 'platform': platform.platform(),
            'cpu': command(['sysctl', '-n', 'machdep.cpu.brand_string']).decode().strip()
            if system[0] == 'Darwin' else Path('/proc/cpuinfo').read_text().splitlines()[:25],
            'clock_ticks_per_second': frequency,
            'cc': command(['cc', '--version']).decode().splitlines()[0]}
