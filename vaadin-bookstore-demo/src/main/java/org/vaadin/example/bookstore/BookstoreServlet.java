package org.vaadin.example.bookstore;

import org.vaadin.example.bookstore.ui.AppShell;
import org.vaadin.example.bookstore.ui.ErrorView;
import org.vaadin.example.bookstore.ui.MainLayout;
import org.vaadin.example.bookstore.ui.about.AboutView;
import org.vaadin.example.bookstore.ui.inventory.InventoryView;
import org.vaadin.example.bookstore.ui.login.LoginScreen;

import java.util.HashMap;
import java.util.Set;
import jakarta.servlet.ServletConfig;
import jakarta.servlet.ServletException;
import com.vaadin.flow.di.Lookup;
import com.vaadin.flow.di.LookupInitializer;
import com.vaadin.flow.function.DeploymentConfiguration;
import com.vaadin.flow.server.ServiceException;
import com.vaadin.flow.server.VaadinServletService;
import com.vaadin.flow.router.InternalServerError;
import com.vaadin.flow.server.VaadinServlet;
import com.vaadin.flow.server.VaadinServletContext;
import com.vaadin.flow.server.startup.ErrorNavigationTargetInitializer;
import com.vaadin.flow.server.startup.RouteRegistryInitializer;
import com.vaadin.flow.server.startup.VaadinAppShellInitializer;
import com.vaadin.flow.server.startup.VaadinInitializerException;

/** Explicit bootstrap replaces classpath/annotation scanning on Android's DEX runtime. */
public final class BookstoreServlet extends VaadinServlet {
    @Override
    public void init(ServletConfig config) throws ServletException {
        VaadinServletContext context = new VaadinServletContext(config.getServletContext());
        if (context.getAttribute(Lookup.class) == null) {
            new LookupInitializer().initialize(context, new HashMap<>(),
                    lookup -> context.setAttribute(Lookup.class, lookup));
            try {
                new RouteRegistryInitializer().initialize(Set.of(MainLayout.class, InventoryView.class, AboutView.class, LoginScreen.class), context);
            } catch (VaadinInitializerException failure) {
                throw new ServletException("Cannot register the demo route", failure);
            }
            new ErrorNavigationTargetInitializer().initialize(
                    Set.of(ErrorView.class, InternalServerError.class), context);
            VaadinAppShellInitializer.init(Set.of(AppShell.class), context);
        }
        super.init(config);
    }

    /** Android uses platform threads; service providers retain the upstream login guard. */
    @Override
    protected VaadinServletService createServletService(DeploymentConfiguration configuration)
            throws ServiceException {
        VaadinServletService service = new VaadinServletService(this, configuration) {
            @Override
            protected java.util.concurrent.Executor createDefaultExecutor() {
                // Android has no virtual threads. The process owns this pool.
                return java.util.concurrent.ForkJoinPool.commonPool();
            }

        };
        service.init();
        return service;
    }
}
