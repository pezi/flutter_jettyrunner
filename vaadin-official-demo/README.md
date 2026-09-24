# Official Vaadin demo — Android WAR port

Source: https://github.com/vaadin/vaadin-demo

Pinned upstream commit: `d362e98aa9c38b588fdcf9f0a74bccbda4da714a`.
The original README is in `UPSTREAM-README.md`; the upstream Unlicense is in
`LICENSE.md`. The Java views, sample data, icons, source viewer, Prism assets,
and view styles are imported from that revision.

WAR Runner deploys `war_repository/vaadin-official-demo.war` at `/`. It includes:

- Dashboard (`/`, `/dashboard`): KPI cards and recent orders.
- Components (`/components`): 19 interactive component examples.
- Products (`/products`): sortable/filterable grid and add/edit dialogs.
- Users (`/users`): avatar grid, name/role filters, invite/edit dialogs.
- Settings (`/settings`): general, notifications, security, and integrations tabs.

The upstream demo uses sample data: save/invite actions show notifications, and
Reports, Analytics, Revenue, Engagement, and Billing are placeholder navigation
items. This port preserves those behaviors. It does not add database persistence,
authentication, invitations, payments, or external integrations.

## Compatibility changes after the Jetty 12 review

All four Vaadin WARs use **Vaadin 25.2.8**, compiled with **Java 21**. The
pinned upstream demo uses 25.1.5; 25.2 fixes a Jetty 12 warning where Flow first
looked up app shell stylesheets such as `styles.css` without a leading slash. The host uses **Jetty 12.1.13 EE11 /
Servlet 6.1**. Merely changing Jetty's version while retaining its EE9 / Servlet 5
module did not enable the upstream Vaadin version.

The Vaadin 24 backport has been removed: `compat/Badge`, `BadgeVariant`,
`ColorScheme`, `android-theme.css`, Lumo substitutions, older Select constructors,
explicit layout references on every route, and duplicate stylesheet registration.
The upstream Aura stylesheet, native badge and color-scheme APIs, `@Layout`,
constructor injection, and original CSS are restored.

Remaining changes are confined to Android deployment:

- `Application` retains the upstream app shell, Aura, stylesheet and favicon;
  the Spring Boot annotation and desktop `main` launcher are removed. Android's
  embedded servlet lifecycle owns startup and shutdown.
- `OfficialDemoServlet` supplies the routes, automatic layout, app shell and
  `SourceService` dependency explicitly. DEX loading does not provide the JVM
  classpath scanning used by Spring and servlet initializers. View constructors
  and route annotations remain upstream code.
- The custom Vaadin servlets use a platform-thread executor. An emulator test with
  Vaadin's default executor fails with `NoSuchMethodError: Thread.ofVirtual`;
  Android does not implement Java virtual threads.
- `AndroidVaadinBytecode.java` changes the virtual-thread pool initialized by
  Flow's `FrontendUtils` to a cached platform-thread pool, only in the bytecode
  passed to D8. The standard JVM WAR is unchanged. This second virtual-thread
  use happens before the servlet service is created, so the executor override
  alone cannot fix it. The transform rejects unexpected upstream call counts.
- Android **15 / API 35** is now the minimum: Flow uses Java 21's `List.getFirst()`.
  Retaining Android 14 would require additional Java API backports.
- `SourceService` uses standard classpath I/O instead of Spring's
  `ClassPathResource`, avoiding a Spring dependency for one resource read.
- Four Grid constructors use `new Grid<>()` instead of the bean-class overload.
  Columns remain exactly as upstream; the bean overload fails with
  `NoClassDefFoundError: java.beans.Introspector`, even with auto-columns disabled.
- The Maven build packages a WAR and the matching official Vaadin production
  frontend bundle. D8 adds Android bytecode; the host provides Servlet 6.1.
  CSS, Prism, icons, source text and dependency notices are bundled locally.
  Application static files are copied to the WAR root; the Android host exposes
  dependency `META-INF/resources` too, including Aura CSS and fonts.
  Desktop development tooling and unused commercial components are excluded.

Upstream's `./mvnw spring-boot:run` remains a desktop JVM command. It is not the
entry point for a WAR running inside an Android application. The packaging and
bootstrap adaptations do not change the demo's sample business behavior.

The existing Hello World and button demos remain separate WARs. Only one demo
runs at a time. Stop the current demo before switching and reload browser tabs
after a restart; server sessions do not survive redeployment.

## Build

From the public repository root:

```sh
bash scripts/build_official_vaadin_war.sh
```

This produces a conventional JVM WAR at
`vaadin-official-demo/target/vaadin-official-demo.war`, then adds multidex and
classpath resources to `war_repository/vaadin-official-demo.war`. Requirements and Android
SDK overrides are documented in the [WAR workspace README](../README.md#build).
No Node.js/frontend build is needed for this port. The separate, private
WAR Runner app downloads published WARs at runtime; its APK contains no WARs.

To inspect or run the unmodified upstream application separately:

```sh
git clone https://github.com/vaadin/vaadin-demo.git
cd vaadin-demo
git checkout d362e98aa9c38b588fdcf9f0a74bccbda4da714a
./mvnw spring-boot:run
```

Use a separate directory: the root project's `vaadin-demo/` already contains the
small button demo. Upstream's development command requires Java 21+ and Maven
downloads; it is independent of the Android WAR build.
