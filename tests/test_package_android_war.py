"""Packaging contract checks; actual D8 and device checks use the demo builds."""

import argparse
import importlib.util
import io
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "package_android_war.py"
spec = importlib.util.spec_from_file_location("package_android_war", SCRIPT)
packager = importlib.util.module_from_spec(spec)
spec.loader.exec_module(packager)


def archive(entries):
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as output:
        for name, content in entries.items():
            output.writestr(name, content)
    return data.getvalue()


class PackagingTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.work = Path(temporary.name)
        self.source_entries = {
            "WEB-INF/web.xml": b"<web-app/>",
            "index.html": b"public page",
            "WEB-INF/classes/demo/App.class": b"app bytecode",
            "WEB-INF/classes/config.properties": b"application settings",
            "WEB-INF/classes/META-INF/services/demo.Service": b"demo.AppProvider\n",
            "WEB-INF/lib/dependency.jar": archive({
                "demo/Library.class": b"library bytecode",
                "META-INF/versions/21/demo/Library.class": b"versioned bytecode",
                "config.properties": b"dependency settings",
                "META-INF/services/demo.Service": b"demo.LibraryProvider\n",
                "META-INF/resources/theme.css": b"body { color: blue; }",
                "META-INF/LICENSE": b"dependency license",
            }),
        }
        source = self.work / "source.war"
        source.write_bytes(archive(self.source_entries))
        self.original = source.read_bytes()
        self.args = argparse.Namespace(
            source=source, output=self.work / "android.war", d8=Path("d8"),
            android_jar=Path("android.jar"), classpath=self.work,
            asm_jar=None, include_jvm=False,
        )

    def compile_dex(self, command, check):
        output = Path(command[command.index("--output") + 1])
        (output / "classes.dex").write_bytes(b"primary dex")
        (output / "classes2.dex").write_bytes(b"secondary dex")

    def package(self):
        with patch.object(packager.subprocess, "run", side_effect=self.compile_dex):
            packager.package(self.args)
        self.assertEqual(self.args.source.read_bytes(), self.original)

    def test_dex_only_preserves_runtime_resources_and_web_paths(self):
        self.package()
        with zipfile.ZipFile(self.args.output) as war:
            self.assertEqual(set(war.namelist()), {
                "WEB-INF/web.xml", "index.html", "WEB-INF/android/runtime.jar",
            })
            self.assertEqual(war.read("WEB-INF/web.xml"), b"<web-app/>")
            self.assertEqual(war.read("index.html"), b"public page")
            with zipfile.ZipFile(io.BytesIO(war.read("WEB-INF/android/runtime.jar"))) as runtime:
                self.assertFalse(any(n.endswith(".class") for n in runtime.namelist()))
                self.assertEqual(runtime.read("classes.dex"), b"primary dex")
                self.assertEqual(runtime.read("classes2.dex"), b"secondary dex")
                self.assertEqual(runtime.read("config.properties"), b"application settings")
                self.assertEqual(runtime.read("META-INF/services/demo.Service"),
                                 b"demo.AppProvider\ndemo.LibraryProvider\n")
                self.assertEqual(runtime.read("META-INF/resources/theme.css"), b"body { color: blue; }")
                self.assertEqual(runtime.read("META-INF/dependency-notices/dependency.jar/META-INF/LICENSE"),
                                 b"dependency license")

    def test_include_jvm_preserves_every_original_file_and_same_runtime(self):
        self.package()
        with zipfile.ZipFile(self.args.output) as war:
            runtime = war.read("WEB-INF/android/runtime.jar")
        self.args.include_jvm = True
        self.package()
        with zipfile.ZipFile(self.args.output) as war:
            for name, content in self.source_entries.items():
                self.assertEqual(war.read(name), content)
            self.assertEqual(war.read("WEB-INF/android/runtime.jar"), runtime)

    def test_failed_conversion_keeps_existing_output(self):
        self.args.output.write_bytes(b"previous distribution")
        with patch.object(packager.subprocess, "run", side_effect=subprocess.CalledProcessError(1, "d8")):
            with self.assertRaises(subprocess.CalledProcessError):
                packager.package(self.args)
        self.assertEqual(self.args.output.read_bytes(), b"previous distribution")
        self.assertEqual(self.args.source.read_bytes(), self.original)


if __name__ == "__main__":
    unittest.main()
