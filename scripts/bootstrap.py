"""Install a pinned, local Windows compiler; never changes system PATH."""
import hashlib
import os
from pathlib import Path
import platform
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
URL = 'https://ziglang.org/download/0.14.1/zig-x86_64-windows-0.14.1.zip'
SHA256 = '554f5378228923ffd558eac35e21af020c73789d87afeabf4bfd16f2e6feed2c'


def install():
    if platform.system() != 'Windows' or platform.machine().lower() not in ('amd64', 'x86_64'):
        raise SystemExit('Use your system GCC/Clang on this platform; portable bootstrap supports Windows x64.')
    target = ROOT / '.tools'
    compiler = target / 'zig-x86_64-windows-0.14.1' / 'zig.exe'
    if compiler.is_file():
        print(compiler)
        return compiler
    target.mkdir(exist_ok=True)
    archive = target / 'zig.zip'
    print('Downloading pinned Zig 0.14.1 from ziglang.org...', flush=True)
    with urllib.request.urlopen(URL, timeout=120) as response, archive.open('wb') as output:
        while chunk := response.read(1024 * 1024):
            output.write(chunk)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != SHA256:
        archive.unlink()
        raise SystemExit('Compiler archive checksum mismatch')
    with zipfile.ZipFile(archive) as bundle:
        for entry in bundle.infolist():
            candidate = (target / entry.filename).resolve()
            if not candidate.is_relative_to(target.resolve()):
                raise SystemExit('Unsafe archive member')
        bundle.extractall(target)
    archive.unlink()
    print(compiler, flush=True)
    return compiler


if __name__ == '__main__':
    install()
