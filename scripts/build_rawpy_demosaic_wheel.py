#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Sequence


DEFAULT_REPO = "https://github.com/exfab/rawpy-demosaic.git"
DEFAULT_REF = "8b17075"


def run(command: Sequence[str], *, cwd: Path | None = None, env: dict[str, str] | None = None) -> None:
    print("==> " + " ".join(command), flush=True)
    subprocess.run(command, cwd=cwd, env=env, check=True)


def patch_setup_py(source_dir: Path) -> None:
    setup_path = source_dir / "setup.py"
    text = setup_path.read_text(encoding="utf-8")
    replacements = {
        "buildGPLCode = False": "buildGPLCode = True",
        "name = 'rawpy'": "name = 'rawpy-demosaic'",
        "License :: OSI Approved :: MIT License": (
            "License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)"
        ),
        "url = 'https://github.com/letmaik/rawpy'": "url = 'https://github.com/exfab/rawpy-demosaic'",
        "-DCMAKE_BUILD_TYPE=Release ": "-DCMAKE_BUILD_TYPE=Release -DCMAKE_POLICY_VERSION_MINIMUM=3.5 ",
        "-DENABLE_EXAMPLES=OFF -DENABLE_OPENMP=ON -DENABLE_RAWSPEED=OFF": (
            "-DENABLE_EXAMPLES=OFF -DENABLE_OPENMP=OFF -DENABLE_RAWSPEED=OFF"
        ),
        (
            "        if not hasOpenMpSupport:\r\n"
            "            raise Exception('OpenMP not available but should be, see error messages above')\r\n"
            "        if is64Bit:"
        ): (
            "        if not hasOpenMpSupport:\r\n"
            "            omp = []\r\n"
            "        elif is64Bit:"
        ),
        (
            "        if not hasOpenMpSupport:\n"
            "            raise Exception('OpenMP not available but should be, see error messages above')\n"
            "        if is64Bit:"
        ): (
            "        if not hasOpenMpSupport:\n"
            "            omp = []\n"
            "        elif is64Bit:"
        ),
        "if isWindows or isMac:": "if isWindows or isMac or buildGPLCode:",
        "elif isMac and needsCompile:": "elif (isMac or (buildGPLCode and not isWindows)) and needsCompile:",
        "    mac_libraw_compile()        \n    \nif any(s in cmdline for s in ['clean', 'sdist']):": (
            "    mac_libraw_compile()        \n"
            "    if not isMac:\n"
            "        package_data['rawpy'] = ['libraw*.so*']\n"
            "    \n"
            "if any(s in cmdline for s in ['clean', 'sdist']):"
        ),
        "include_dirs += [numpy.get_include()]": (
            "include_dirs += [numpy.get_include()]\n"
            "if buildGPLCode and not isWindows and not isMac:\n"
            "    extra_link_args += ['-Wl,-rpath,$ORIGIN']"
        ),
        "    os.chdir(cwd)\n        \npackage_data = {}": (
            "    os.chdir(cwd)\n"
            "    if not isMac:\n"
            "        lib_dir = os.path.join(install_dir, 'lib')\n"
            "        for filename in os.listdir(lib_dir):\n"
            "            if filename.startswith('libraw') and '.so' in filename:\n"
            "                shutil.copyfile(os.path.join(lib_dir, filename), os.path.join('rawpy', filename))\n"
            "        \n"
            "package_data = {}"
        ),
        (
            "        cmakelists_patched = re.sub(r'INSTALL\\(TARGETS raw(.*?)\\)', "
            "add_optional, cmakelists, count=1, flags=re.DOTALL)"
        ): (
            "        cmakelists_patched = re.sub(r'INSTALL\\(TARGETS raw(.*?)\\)', "
            "add_optional, cmakelists, count=1, flags=re.DOTALL)\n"
            "        cmakelists_patched = cmakelists_patched.replace("
            "\"DESTINATION ${INSTALL_CMAKE_MODULE_PATH}\", \"DESTINATION cmake\")"
        ),
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    setup_path.write_text(text, encoding="utf-8")


def patch_libraw_sources(source_dir: Path) -> None:
    dcraw_common = source_dir / "external" / "LibRaw" / "internal" / "dcraw_common.cpp"
    if not dcraw_common.exists():
        return
    text = dcraw_common.read_text(encoding="utf-8", errors="surrogateescape")
    text = text.replace("powf64", "libraw_powf64")
    dcraw_common.write_text(text, encoding="utf-8", errors="surrogateescape")

    cmakelists = source_dir / "external" / "LibRaw" / "CMakeLists.txt"
    if cmakelists.exists():
        cmake_text = cmakelists.read_text(encoding="utf-8", errors="surrogateescape")
        cmake_text = cmake_text.replace("DESTINATION ${INSTALL_CMAKE_MODULE_PATH}", "DESTINATION cmake")
        cmakelists.write_text(cmake_text, encoding="utf-8", errors="surrogateescape")


def patch_rawpy_sources(source_dir: Path) -> None:
    rawpy_pyx = source_dir / "rawpy" / "_rawpy.pyx"
    if not rawpy_pyx.exists():
        return
    text = rawpy_pyx.read_text(encoding="utf-8", errors="surrogateescape")
    text = text.replace(
        "            ndarr.base = <PyObject*> self\n"
        "            # Python doesn't know about above assignment as it's in C-level \n"
        "            Py_INCREF(self)\n",
        "            np.set_array_base(ndarr, self)\n",
    )
    text = text.replace(
        "        ndarr.base = <PyObject*> self\n"
        "        # Python doesn't know about above assignment as it's in C-level \n"
        "        Py_INCREF(self)\n",
        "        np.set_array_base(ndarr, self)\n",
    )
    rawpy_pyx.write_text(text, encoding="utf-8", errors="surrogateescape")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Construye una wheel rawpy-demosaic con AMaZE/GPL3 activado.")
    parser.add_argument("--python", default=sys.executable, help="Python/venv usado para construir la wheel.")
    parser.add_argument("--repo", default=DEFAULT_REPO, help="Repositorio Git rawpy-demosaic.")
    parser.add_argument("--ref", default=DEFAULT_REF, help="Commit/tag Git de rawpy-demosaic.")
    parser.add_argument("--work-dir", required=True, help="Directorio temporal de trabajo.")
    parser.add_argument("--output-dir", required=True, help="Directorio donde dejar la wheel generada.")
    parser.add_argument("--force", action="store_true", help="Elimina work-dir si ya existe.")
    args = parser.parse_args(argv)

    python = Path(args.python).expanduser()
    work_dir = Path(args.work_dir).expanduser()
    output_dir = Path(args.output_dir).expanduser()
    source_dir = work_dir / "rawpy-demosaic"

    if work_dir.exists() and args.force:
        shutil.rmtree(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not source_dir.exists():
        run(
            [
                "git",
                "-c",
                "url.https://github.com/.insteadOf=git://github.com/",
                "clone",
                "--recursive",
                args.repo,
                str(source_dir),
            ]
        )
    run(["git", "-C", str(source_dir), "checkout", args.ref])
    run(["git", "-C", str(source_dir), "submodule", "sync", "--recursive"])
    run(
        [
            "git",
            "-C",
            str(source_dir),
            "-c",
            "url.https://github.com/.insteadOf=git://github.com/",
            "submodule",
            "update",
            "--init",
            "--recursive",
        ]
    )

    patch_setup_py(source_dir)
    patch_libraw_sources(source_dir)
    patch_rawpy_sources(source_dir)
    build_env = os.environ.copy()
    build_env["PATH"] = str(python.parent) + os.pathsep + build_env.get("PATH", "")
    run(
        [str(python), "-m", "pip", "install", "--upgrade", "setuptools<70", "wheel", "Cython>=3.1", "numpy", "cmake>=3.27"],
        cwd=source_dir,
        env=build_env,
    )
    run([str(python), "setup.py", "bdist_wheel"], cwd=source_dir, env=build_env)

    wheels = sorted((source_dir / "dist").glob("rawpy_demosaic-*.whl"))
    if not wheels:
        print("ERROR: no se genero ninguna wheel rawpy_demosaic-*.whl", file=sys.stderr)
        return 2
    wheel = wheels[-1]
    dest = output_dir / wheel.name
    shutil.copy2(wheel, dest)
    print(dest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
