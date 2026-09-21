package app.flutterdev.addressbook;

/** A contact of the address book. Mutable bean so the Vaadin {@code Binder} can write back into it. */
public final class Person {
    private Long id;
    private String firstName = "";
    private String lastName = "";
    private String email = "";
    private String phone = "";
    private String street = "";
    private String postalCode = "";
    private String city = "";

    public Person() {
    }

    public Person(Long id, String firstName, String lastName, String email, String phone,
            String street, String postalCode, String city) {
        this.id = id;
        this.firstName = firstName;
        this.lastName = lastName;
        this.email = email;
        this.phone = phone;
        this.street = street;
        this.postalCode = postalCode;
        this.city = city;
    }

    public boolean isNew() {
        return id == null;
    }

    public String getFullName() {
        return (firstName + " " + lastName).trim();
    }

    /** Case-insensitive match against every visible field, for the search box. */
    public boolean matches(String query) {
        String needle = query.toLowerCase();
        return contains(firstName, needle) || contains(lastName, needle) || contains(email, needle)
                || contains(phone, needle) || contains(street, needle) || contains(postalCode, needle)
                || contains(city, needle);
    }

    private static boolean contains(String value, String needle) {
        return value != null && value.toLowerCase().contains(needle);
    }

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public String getFirstName() { return firstName; }
    public void setFirstName(String firstName) { this.firstName = firstName; }
    public String getLastName() { return lastName; }
    public void setLastName(String lastName) { this.lastName = lastName; }
    public String getEmail() { return email; }
    public void setEmail(String email) { this.email = email; }
    public String getPhone() { return phone; }
    public void setPhone(String phone) { this.phone = phone; }
    public String getStreet() { return street; }
    public void setStreet(String street) { this.street = street; }
    public String getPostalCode() { return postalCode; }
    public void setPostalCode(String postalCode) { this.postalCode = postalCode; }
    public String getCity() { return city; }
    public void setCity(String city) { this.city = city; }
}
