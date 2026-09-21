package app.flutterdev.vaadindemo;

import com.vaadin.flow.component.button.Button;
import com.vaadin.flow.component.button.ButtonVariant;
import com.vaadin.flow.component.html.Div;
import com.vaadin.flow.component.html.H1;
import com.vaadin.flow.component.html.Paragraph;
import com.vaadin.flow.component.html.Span;
import com.vaadin.flow.component.orderedlayout.VerticalLayout;
import com.vaadin.flow.router.PageTitle;
import com.vaadin.flow.router.Route;
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;

@Route("")
@PageTitle("Vaadin on Android")
public final class DemoView extends VerticalLayout {
    private static final DateTimeFormatter TIME = DateTimeFormatter.ofPattern("HH:mm:ss");
    private int presses;

    public DemoView() {
        Span message = new Span("Waiting for a button press.");
        message.setId("message");
        message.getElement().setAttribute("role", "status");
        Div log = new Div();
        log.setId("log");
        log.getStyle().set("font-family", "monospace").set("white-space", "pre-line");
        Button button = new Button("Press button", event -> {
            presses++;
            String line = "Button pressed #" + presses + " at " + LocalTime.now().format(TIME);
            message.setText(presses == 1 ? "Button pressed once." : "Button pressed " + presses + " times.");
            log.addComponentAsFirst(new Div(line));
            // Also visible in the web admin console of the app.
            System.out.println(line);
        });
        button.setId("press-button");
        button.addThemeVariants(ButtonVariant.PRIMARY);
        add(new H1("Vaadin on Android"),
                new Paragraph("A Vaadin Flow view running inside Jetty on your phone. Every press adds a line."),
                button, message, log);
        setMaxWidth("640px");
        getStyle().set("margin", "3rem auto");
        setPadding(true);
        setSpacing(true);
    }
}
