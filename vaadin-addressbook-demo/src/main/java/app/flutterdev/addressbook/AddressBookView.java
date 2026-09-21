package app.flutterdev.addressbook;

import com.vaadin.flow.component.avatar.Avatar;
import com.vaadin.flow.component.button.Button;
import com.vaadin.flow.component.button.ButtonVariant;
import com.vaadin.flow.component.grid.Grid;
import com.vaadin.flow.component.grid.GridVariant;
import com.vaadin.flow.component.html.Div;
import com.vaadin.flow.component.html.H1;
import com.vaadin.flow.component.html.Paragraph;
import com.vaadin.flow.component.html.Span;
import com.vaadin.flow.component.icon.Icon;
import com.vaadin.flow.component.icon.VaadinIcon;
import com.vaadin.flow.component.notification.Notification;
import com.vaadin.flow.component.notification.NotificationVariant;
import com.vaadin.flow.component.orderedlayout.HorizontalLayout;
import com.vaadin.flow.component.orderedlayout.VerticalLayout;
import com.vaadin.flow.component.page.Page;
import com.vaadin.flow.component.textfield.TextField;
import com.vaadin.flow.data.value.ValueChangeMode;
import com.vaadin.flow.router.PageTitle;
import com.vaadin.flow.router.Route;
import java.util.List;

/** Searchable contact list with an add/edit dialog, backed by {@link PersonRepository}. */
@Route("")
@PageTitle("Address Book")
public final class AddressBookView extends VerticalLayout {
    private final PersonRepository repository;
    private final Grid<Person> grid = new Grid<>();
    private final TextField search = new TextField();
    private final Span count = new Span();
    private final Div empty = new Div();
    private final PersonForm form;

    public AddressBookView(PersonRepository repository) {
        this.repository = repository;
        addClassName("address-book");
        setSizeFull();
        setPadding(false);
        setSpacing(false);

        form = new PersonForm(this::save, this::delete);

        Icon logo = VaadinIcon.USERS.create();
        logo.addClassName("logo");
        H1 title = new H1("Address Book");
        Paragraph subtitle = new Paragraph("Contacts live in an in-memory H2 database inside Jetty on this phone.");
        subtitle.addClassName("subtitle");
        Div heading = new Div(title, subtitle);
        heading.addClassName("heading");
        count.addClassName("count");
        HorizontalLayout header = new HorizontalLayout(logo, heading, count);
        header.addClassName("header");
        header.setAlignItems(Alignment.CENTER);
        header.setWidthFull();

        search.setPlaceholder("Search contacts");
        search.setPrefixComponent(VaadinIcon.SEARCH.create());
        search.setClearButtonVisible(true);
        search.setValueChangeMode(ValueChangeMode.LAZY);
        search.addValueChangeListener(event -> refresh());
        search.addClassName("search");
        Button add = new Button("New contact", VaadinIcon.PLUS.create(), event -> form.edit(new Person()));
        add.addThemeVariants(ButtonVariant.LUMO_PRIMARY);
        HorizontalLayout toolbar = new HorizontalLayout(search, add);
        toolbar.addClassName("toolbar");
        toolbar.setWidthFull();
        toolbar.setAlignItems(Alignment.CENTER);
        toolbar.expand(search);

        grid.addThemeVariants(GridVariant.LUMO_ROW_STRIPES, GridVariant.LUMO_WRAP_CELL_CONTENT);
        grid.addClassName("contacts");
        grid.setSizeFull();
        // The name column takes the remaining width so the grid never scrolls sideways on phones.
        grid.addComponentColumn(this::nameCell).setHeader("Name").setFlexGrow(2)
                .setComparator((a, b) -> a.getFullName().compareToIgnoreCase(b.getFullName()));
        grid.addColumn(Person::getPhone).setHeader("Phone").setAutoWidth(true).setFlexGrow(1);
        Grid.Column<Person> address = grid.addComponentColumn(this::addressCell).setHeader("Address")
                .setAutoWidth(true).setFlexGrow(2)
                .setComparator((a, b) -> a.getCity().compareToIgnoreCase(b.getCity()));
        Grid.Column<Person> actions = grid.addComponentColumn(person -> {
            Button edit = new Button(VaadinIcon.EDIT.create(), event -> form.edit(person));
            edit.addThemeVariants(ButtonVariant.LUMO_TERTIARY, ButtonVariant.LUMO_ICON, ButtonVariant.LUMO_SMALL);
            edit.setAriaLabel("Edit " + person.getFullName());
            return edit;
        }).setWidth("64px").setFlexGrow(0);
        grid.addItemClickListener(event -> form.edit(event.getItem()));
        // Phones: keep name and phone only; tapping a row still opens the editor.
        addAttachListener(attached -> {
            Page page = attached.getUI().getPage();
            page.retrieveExtendedClientDetails(details -> narrow(details.getBodyClientWidth(), address, actions));
            page.addBrowserWindowResizeListener(resized -> narrow(resized.getWidth(), address, actions));
        });

        empty.addClassName("empty");
        empty.setVisible(false);

        Div page = new Div(header, toolbar, grid, empty);
        page.addClassName("page");
        page.setSizeFull();
        add(page);
        refresh();
    }

    private static void narrow(int width, Grid.Column<Person> address, Grid.Column<Person> actions) {
        boolean wide = width >= 640;
        address.setVisible(wide);
        actions.setVisible(wide);
    }

    private Div nameCell(Person person) {
        Avatar avatar = new Avatar(person.getFullName());
        avatar.setColorIndex((int) (person.getId() == null ? 0 : person.getId() % 7));
        Span name = new Span(person.getFullName());
        name.addClassName("name");
        Span email = new Span(person.getEmail());
        email.addClassName("email");
        Div text = new Div(name, email);
        text.addClassName("name-text");
        Div cell = new Div(avatar, text);
        cell.addClassName("name-cell");
        return cell;
    }

    private Div addressCell(Person person) {
        Span street = new Span(person.getStreet());
        Span city = new Span((person.getPostalCode() + " " + person.getCity()).trim());
        city.addClassName("city");
        Div cell = new Div(street, city);
        cell.addClassName("address-cell");
        return cell;
    }

    private void refresh() {
        List<Person> people = repository.search(search.getValue());
        grid.setItems(people);
        long total = repository.count();
        count.setText(total == 1 ? "1 contact" : total + " contacts");
        boolean nothing = people.isEmpty();
        empty.setText(total == 0 ? "The address book is empty. Add your first contact."
                : "No contact matches \"" + search.getValue().trim() + "\".");
        empty.setVisible(nothing);
        grid.setVisible(!nothing);
    }

    private void save(Person person) {
        boolean created = person.isNew();
        repository.save(person);
        refresh();
        notify((created ? "Added " : "Saved ") + person.getFullName(), NotificationVariant.LUMO_SUCCESS);
        System.out.println((created ? "Added contact " : "Saved contact ") + person.getFullName());
    }

    private void delete(Person person) {
        repository.delete(person);
        refresh();
        notify("Deleted " + person.getFullName(), NotificationVariant.LUMO_CONTRAST);
        System.out.println("Deleted contact " + person.getFullName());
    }

    private static void notify(String text, NotificationVariant variant) {
        Notification notification = Notification.show(text, 2500, Notification.Position.BOTTOM_CENTER);
        notification.addThemeVariants(variant);
    }
}
