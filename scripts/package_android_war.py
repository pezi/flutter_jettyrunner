#!/usr/bin/env python3
"""Add a DEX + resource classpath to a conventional WAR without changing its JVM deployment."""

import argparse
import io
import pathlib
import subprocess
import tempfile
import zipfile


def write_zip(destination, entries):
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as output:
        for name, content in sorted(entries.items()):
            entry = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o100644 << 16
            output.writestr(entry, content)


def package(args):
    classes = {}
    resources = {}
    services = {}

    def collect(name, content, origin):
        if name.endswith("/") or name.startswith("META-INF/versions/") or name == "module-info.class":
            return
        if name.endswith(".class"):
            if name in classes and classes[name] != content:
                raise ValueError(f"Conflicting class {name} in {origin}")
            classes[name] = content
        elif name.startswith("META-INF/services/"):
            providers = services.setdefault(name, set())
            providers.update(line.split("#", 1)[0].strip() for line in content.decode().splitlines())
            providers.discard("")
        elif name.upper().endswith((".SF", ".RSA", ".DSA")) or name == "META-INF/MANIFEST.MF":
            return
        else:
            resources.setdefault(name, content)
            if "LICENSE" in name.upper() or "NOTICE" in name.upper():
                resources[f"META-INF/dependency-notices/{origin}/{name}"] = content

    with zipfile.ZipFile(args.source) as war:
        entries = {entry.filename: war.read(entry) for entry in war.infolist() if not entry.is_dir()}
    library_names = set()
    # Application resources take precedence over dependency resources.
    for name, content in entries.items():
        if name.startswith("WEB-INF/classes/"):
            collect(name.removeprefix("WEB-INF/classes/"), content, "application")
    for name, content in sorted(entries.items()):
        if name.startswith("WEB-INF/lib/") and name.endswith(".jar"):
            library_names.add(pathlib.PurePosixPath(name).name)
            with zipfile.ZipFile(io.BytesIO(content)) as library:
                for entry in library.infolist():
                    collect(entry.filename, library.read(entry), pathlib.PurePosixPath(name).name)
    for name, providers in services.items():
        resources[name] = ("\n".join(sorted(providers)) + "\n").encode()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="android-war-", dir=args.source.parent) as temporary:
        work = pathlib.Path(temporary)
        if args.asm_jar:
            # Keep the JVM WAR untouched. Adapt only the bytecode passed to D8.
            name = "com/vaadin/flow/internal/FrontendUtils.class"
            frontend_utils = work / "FrontendUtils.class"
            frontend_utils.write_bytes(classes[name])
            subprocess.run(["java", "-cp", str(args.asm_jar),
                            str(pathlib.Path(__file__).with_name("AndroidVaadinBytecode.java")),
                            str(frontend_utils)], check=True)
            classes[name] = frontend_utils.read_bytes()
        program = work / "program.jar"
        write_zip(program, classes)
        dex = work / "dex"
        dex.mkdir()
        command = [str(args.d8), "--release", "--min-api", "35", "--lib", str(args.android_jar),
                   "--output", str(dex)]
        for jar in sorted(args.classpath.glob("*.jar")):
            if jar.name not in library_names:
                command.extend(["--classpath", str(jar)])
        subprocess.run([*command, str(program)], check=True)
        dex_files = sorted(dex.glob("classes*.dex"))
        if not dex_files:
            raise RuntimeError("D8 produced no bytecode")
        resources.update({file.name: file.read_bytes() for file in dex_files})
        runtime = work / "runtime.jar"
        write_zip(runtime, resources)
        entries["WEB-INF/android/runtime.jar"] = runtime.read_bytes()
        output = work / "android.war"
        write_zip(output, entries)
        output.replace(args.output)
    print(f"Built {args.output}: {len(classes)} classes, {len(dex_files)} DEX files, "
          f"{args.output.stat().st_size:,} bytes")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=pathlib.Path)
    parser.add_argument("output", type=pathlib.Path)
    parser.add_argument("--d8", type=pathlib.Path, required=True)
    parser.add_argument("--android-jar", type=pathlib.Path, required=True)
    parser.add_argument("--classpath", type=pathlib.Path, required=True)
    parser.add_argument("--asm-jar", type=pathlib.Path,
                        help="ASM build tool for the Vaadin 25 Android-only virtual-thread adjustment")
    package(parser.parse_args())
