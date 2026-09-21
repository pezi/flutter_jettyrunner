# Runner WAR applications

This workspace contains the demo applications, Android WAR packaging tools,
download catalog, and publishing scripts for **WAR Runner**. 
The app downloads published WARs at runtime; its APK contains no WAR files.

```text
├── servlet/                 # Hello World servlet
├── vaadin-demo/             # Vaadin button demo
├── vaadin-official-demo/    # Official Vaadin demo port
├── vaadin-bookstore-demo/   # Vaadin Bookstore port
├── vaadin-addressbook-demo/ # Address book on an in-memory H2 database
├── scripts/                 # Build, DEX packaging, catalog and publishing
├── docs/WAR_CONVERSION.md  # Conversion contract and validation history
└── war_repository/         # demos.json, generated wars.json and Android WARs
```


## Build

Requirements: Maven, JDK **21+** for Vaadin (**11+** for Hello World), Python
**3.9+**, Android SDK Build-Tools **36.0.0**, and Android SDK Platform **36**.
The bookstore also builds its production frontend and needs Node.js/npm;
Vaadin installs a supported Node version if necessary.

The build scripts find the Android SDK in this order:

1. `ANDROID_SDK_ROOT`.
2. `ANDROID_HOME`.
3. `sdk.dir` in the sibling `../jettyrunner/android/local.properties`.

For a standalone checkout, set either SDK environment variable. Optional
`ANDROID_BUILD_TOOLS` and `ANDROID_COMPILE_API` overrides select other installed
tool/platform versions; `ANDROID_COMPILE_API` applies to the Vaadin packager.

Run from `jettyrunner_github/`:

```sh
bash scripts/build_war.sh                  # Hello World
bash scripts/build_vaadin_war.sh           # Vaadin button
bash scripts/build_official_vaadin_war.sh  # Official Vaadin demo
bash scripts/build_bookstore_war.sh        # Vaadin Bookstore
bash scripts/build_addressbook_war.sh      # Vaadin Address Book (H2)
python3 scripts/generate_war_catalog.py
```

Scripts locate sources and outputs relative to their own location. They also
work from the app directory, for example:

```sh
bash ./scripts/build_war.sh
```

| Application | Standard JVM WAR | Android distribution WAR |
| --- | --- | --- |
| Hello World | `servlet/target/hello.war` | `war_repository/hello.war` |
| Vaadin button | `vaadin-demo/target/vaadin-demo.war` | `war_repository/vaadin-demo.war` |
| Official Vaadin demo | `vaadin-official-demo/target/vaadin-official-demo.war` | `war_repository/vaadin-official-demo.war` |
| Vaadin Bookstore | `vaadin-bookstore-demo/target/vaadin-bookstore-demo.war` | `war_repository/vaadin-bookstore-demo.war` |
| Vaadin Address Book | `vaadin-addressbook-demo/target/vaadin-addressbook-demo.war` | `war_repository/vaadin-addressbook-demo.war` |

The Android WAR adds executable DEX bytecode while retaining the conventional
JVM WAR contents. `package_android_war.py` and its adjacent
`AndroidVaadinBytecode.java` package the Vaadin runtime and compatibility fixes.
Read the [conversion guide](docs/WAR_CONVERSION.md) before adding another WAR or
upgrading dependencies. Arbitrary desktop WARs need Android conversion first.

