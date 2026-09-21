package app.flutterdev.addressbook;

import com.vaadin.flow.component.button.Button;
import com.vaadin.flow.component.button.ButtonVariant;
import com.vaadin.flow.component.confirmdialog.ConfirmDialog;
import com.vaadin.flow.component.dialog.Dialog;
import com.vaadin.flow.component.formlayout.FormLayout;
import com.vaadin.flow.component.icon.VaadinIcon;
import com.vaadin.flow.component.textfield.EmailField;
import com.vaadin.flow.component.textfield.TextField;
import com.vaadin.flow.data.binder.Binder;
import com.vaadin.flow.data.validator.EmailValidator;
import java.util.function.Consumer;

/** Dialog for adding or editing one contact. */
final class PersonForm extends Dialog {
    private final Binder<Person> binder = new Binder<>();
    private final Button delete = new Button("Delete", VaadinIcon.TRASH.create());
    private final Button save = new Button("Save");
    private Person person;

    PersonForm(Consumer<Person> onSave, Consumer<Person> onDelete) {
        setCloseOnOutsideClick(false);
        setWidth("min(560px, 96vw)");
        addClassName("person-form");

        TextField firstName = new TextField("First name");
        TextField lastName = new TextField("Last name");
        EmailField email = new EmailField("Email");
        TextField phone = new TextField("Phone");
        TextField street = new TextField("Street");
        TextField postalCode = new TextField("Postal code");
        TextField city = new TextField("City");
        firstName.setAutofocus(true);
        phone.setPlaceholder("+43 660 000 0000");
        for (TextField field : new TextField[] {firstName, lastName, phone, street, postalCode, city}) {
            field.setClearButtonVisible(true);
        }
        email.setClearButtonVisible(true);

        FormLayout form = new FormLayout(firstName, lastName, email, phone, street, postalCode, city);
        form.setResponsiveSteps(new FormLayout.ResponsiveStep("0", 1), new FormLayout.ResponsiveStep("420px", 2));
        form.setColspan(email, 2);
        form.setColspan(street, 2);
        add(form);

        // Android omits java.beans.Introspector: bind each field explicitly instead of
        // Binder(Person.class) / bindInstanceFields.
        binder.forField(firstName).asRequired("Enter a first name").bind(Person::getFirstName, Person::setFirstName);
        binder.forField(lastName).asRequired("Enter a last name").bind(Person::getLastName, Person::setLastName);
        binder.forField(email).asRequired("Enter an email address")
                .withValidator(new EmailValidator("This does not look like an email address"))
                .bind(Person::getEmail, Person::setEmail);
        binder.forField(phone).bind(Person::getPhone, Person::setPhone);
        binder.forField(street).bind(Person::getStreet, Person::setStreet);
        binder.forField(postalCode).bind(Person::getPostalCode, Person::setPostalCode);
        binder.forField(city).bind(Person::getCity, Person::setCity);
        // isValid() checks every binding silently, so untouched required fields keep Save disabled
        // without painting errors before the user has typed anything.
        binder.addStatusChangeListener(event -> save.setEnabled(binder.isValid()));

        save.addThemeVariants(ButtonVariant.LUMO_PRIMARY);
        save.addClickShortcut(com.vaadin.flow.component.Key.ENTER);
        save.addClickListener(event -> {
            if (binder.writeBeanIfValid(person)) {
                close();
                onSave.accept(person);
            }
        });
        Button cancel = new Button("Cancel", event -> close());
        delete.addThemeVariants(ButtonVariant.LUMO_ERROR, ButtonVariant.LUMO_TERTIARY);
        delete.addClickListener(event -> {
            ConfirmDialog confirm = new ConfirmDialog("Delete " + person.getFullName() + "?",
                    "This removes the contact from the address book.", "Delete", confirmed -> {
                        close();
                        onDelete.accept(person);
                    }, "Cancel", cancelled -> { });
            confirm.setConfirmButtonTheme("error primary");
            confirm.open();
        });
        getFooter().add(delete, cancel, save);
    }

    void edit(Person person) {
        this.person = person;
        setHeaderTitle(person.isNew() ? "New contact" : person.getFullName());
        delete.setVisible(!person.isNew());
        binder.readBean(person);
        save.setEnabled(binder.isValid());
        open();
    }
}
