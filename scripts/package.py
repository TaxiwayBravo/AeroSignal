"""Build a credential-free distributable from an explicit allowlist."""
import hashlib
from pathlib import Path
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FILES = ['README.md', 'LICENSE', 'THIRD_PARTY.md', 'compose.yaml', 'Dockerfile', '.dockerignore', '.gitignore', '.gitattributes']
DIRS = ['app', 'scripts', 'tests', 'docs', '.github']


def main():
    dest = ROOT / 'release'
    dest.mkdir(exist_ok=True)
    files = [ROOT / f for f in FILES]
    files += [p for d in DIRS for p in (ROOT / d).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc']
    with zipfile.ZipFile(dest / 'aerosignal-1.0.0.zip', 'w', zipfile.ZIP_DEFLATED) as z:
        for p in files:
            z.write(p, 'aerosignal/' + p.relative_to(ROOT).as_posix())
    with tarfile.open(dest / 'aerosignal-1.0.0.tar.gz', 'w:gz') as t:
        for p in files:
            t.add(p, arcname='aerosignal/' + p.relative_to(ROOT).as_posix())
    sums = []
    for p in sorted(dest.glob('aerosignal-1.0.0.*')):
        sums.append(hashlib.sha256(p.read_bytes()).hexdigest() + '  ' + p.name)
    (dest / 'SHA256SUMS').write_text('\n'.join(sums) + '\n')
    print('\n'.join(sums))


if __name__ == '__main__':
    main()
