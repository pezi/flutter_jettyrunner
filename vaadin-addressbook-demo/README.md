# Vaadin Address Book demo

A small contact manager: search, add, edit and delete people. No login. The
data lives in an **in-memory H2 database** inside the running web app and starts
with five demo contacts every time the WAR is started.

## Persistence without Spring

The [Vaadin persistence guide](https://vaadin.com/docs/latest/building-apps/forms-data/persistence/add-spring-data)
stores the same kind of `Person` through Spring Data JPA. Spring Boot and
Hibernate generate classes at run time and scan the classpath, which Android's
DEX runtime does not support, so this demo keeps the guide's shape and swaps
the implementation:

| Guide | This demo |
| --- | --- |
| `@Entity Person` | `Person` bean with explicit getters and setters |
| `PersonRepository extends JpaRepository` | `PersonRepository` over plain JDBC (`find`, `search`, `save`, `delete`) |
| Spring constructor injection into the view | `AddressBookServlet` creates one repository and hands it to `AddressBookView` through a custom `Instantiator` |
| `application.properties` data source | `jdbc:h2:mem:addressbook` opened with `org.h2.Driver.connect` |

The H2 connection is opened through the driver directly. `DriverManager` and
H2's JNDI-backed data sources are avoided because `javax.naming` is missing on
Android. The form uses explicit `Binder` bindings instead of
`Binder(Person.class)` because Android has no `java.beans.Introspector`.

## Build

From the public repository root, using the [shared build requirements](../README.md#build):

```sh
bash scripts/build_addressbook_war.sh
python3 scripts/generate_war_catalog.py
```

The WAR uses Vaadin 25.2.8 with the pre-built production bundle and the Aura
theme, like the button demo.
