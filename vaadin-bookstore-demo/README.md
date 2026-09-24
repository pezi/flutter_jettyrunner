# Vaadin Bookstore — Android demo 4

Android port of [vaadin/bookstore-example](https://github.com/vaadin/bookstore-example),
branch `v25`, pinned to commit
[`a86110dab30778dac47ed5eeed7c606ee67937c3`](https://github.com/vaadin/bookstore-example/tree/a86110dab30778dac47ed5eeed7c606ee67937c3).
The upstream application uses **Vaadin 25.2.8** and Java 21; this port keeps that
version. All four Vaadin demos in this repository now use 25.2.8.

Select **Vaadin Bookstore demo**, start the servlet, and open the displayed URL.
Log in with **admin / admin** to edit books and categories. Any other matching
username/password pair (for example **user / user**) uses upstream's browsing
role. This is the original sample authentication, not production security.
The mock backend stores changes in memory for the current deployment; stopping
and restarting the demo resets the sample data.

## What is preserved

Inventory and its root alias, product selection/filtering/sorting and editing,
category administration, About, login/logout, the login navigation guard,
service-provider registration, Lumo styling, custom CSS, images and generated
sample data come from upstream. The Admin route is still registered per session
only when an administrator signs in. The upstream README and POM are retained
as `UPSTREAM-README.md` and `UPSTREAM-pom.xml`. The pinned upstream tree contains
no standalone license file; this port does not invent or replace its licensing.
Dependency notices are retained by the Android packager.

## Android adaptations

- `BookstoreServlet` explicitly registers routes, the error view and app shell,
  replacing desktop annotation scanning. The original `BookstoreInitListener`
  is discovered through its preserved service-provider resource.
- The servlet uses a process-owned platform-thread pool. The existing checked
  bytecode transformation also adapts Flow's frontend utility executor before
  D8; JVM classes in the conventional WAR remain unchanged.
- `ProductForm` and `AdminView` use explicit `Binder` getters/setters and the
  same field constraints instead of `BeanValidationBinder` and property names.
  Android does not provide `java.beans.Introspector`, which reflective binding
  requires. Product/category names retain their two-character minimum, prices
  and stock remain nonnegative, and availability remains required. The model's
  original validation annotations are retained; Hibernate Validator is not
  needed for these explicit bindings.
- A Servlet 6.1 `metadata-complete` descriptor configures production mode and
  the existing Jetty EE11 host. Servlet and logging APIs come from the host.
- Maven builds the application's real production frontend, including both
  original `@CssImport` stylesheets and its Lumo theme. This differs from the
  standard prebuilt frontend used by demos 2 and 3.

## Rebuild

From the public repository root:

```sh
bash scripts/build_bookstore_war.sh
```

Requires the tools in [the conversion guide](../docs/WAR_CONVERSION.md), plus
Node.js/npm for Vaadin's production frontend build. The initial build may
install frontend dependencies. Outputs are the conventional JVM WAR in
`vaadin-bookstore-demo/target/vaadin-bookstore-demo.war` and the downloadable Android WAR
`war_repository/vaadin-bookstore-demo.war`. The separate WAR Runner app downloads
published WARs at runtime; its private Flutter source is not required for this build.
