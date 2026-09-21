"""生成不含本地环境、缓存、视频和凭据的 Linux/Windows 源码部署包。"""

import argparse
import hashlib
import io
from pathlib import Path
import tarfile
import zipfile


PROJECT_ROOT = Path(__file__).resolve().parent
PACKAGE_NAME = "douyin-original-parser"


def package_files():
    files = [PROJECT_ROOT / name for name in (
        "run.py", "parse_links.py", "requirements.txt", "README.md", "package.py", "package.ps1",
    )]
    files.extend(sorted((PROJECT_ROOT / "original_parser").glob("*.py")))
    files.extend(PROJECT_ROOT / name for name in (
        "deploy/README.md",
        "deploy/linux/install.sh",
        "deploy/linux/start.sh",
        "deploy/linux/douyin-original-parser.service",
        "deploy/windows/install.ps1",
        "deploy/windows/start.ps1",
    ))
    for path in files:
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"打包文件缺失或是符号链接：{path}")
        relative = path.relative_to(PROJECT_ROOT).as_posix()
        # Linux 脚本统一 LF；PowerShell 脚本带 BOM，兼容 Windows PowerShell 5.1。
        source = path.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
        encoding = "utf-8-sig" if path.suffix == ".ps1" else "utf-8"
        yield relative, source.encode(encoding)


def main():
    parser = argparse.ArgumentParser(description="生成自建原画服务部署包")
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT.parent)
    args = parser.parse_args()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    files = list(package_files())
    zip_path = output_dir / f"{PACKAGE_NAME}-deploy.zip"
    tar_path = output_dir / f"{PACKAGE_NAME}-deploy.tar.gz"
    for path in (zip_path, tar_path):
        if path.is_symlink():
            raise ValueError(f"输出位置不能是符号链接：{path}")
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for relative, content in files:
            entry = zipfile.ZipInfo(f"{PACKAGE_NAME}/{relative}")
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.create_system = 3
            entry.external_attr = (0o100755 if relative.endswith(".sh") else 0o100644) << 16
            archive.writestr(entry, content)
    with tarfile.open(tar_path, "w:gz", format=tarfile.PAX_FORMAT) as archive:
        for relative, content in files:
            entry = tarfile.TarInfo(f"{PACKAGE_NAME}/{relative}")
            entry.size = len(content)
            entry.mode = 0o755 if relative.endswith(".sh") else 0o644
            entry.uid = entry.gid = 0
            entry.uname = entry.gname = "root"
            archive.addfile(entry, io.BytesIO(content))
    checksums = []
    for path in (zip_path, tar_path):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        checksums.append(f"{digest}  {path.name}\n")
        print(f"{path} ({path.stat().st_size:,} bytes, {len(files)} files)")
    (output_dir / f"{PACKAGE_NAME}-deploy.sha256").write_text("".join(checksums), encoding="ascii")


if __name__ == "__main__":
    main()
