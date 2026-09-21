package com.vaadin.demo;

import com.vaadin.demo.ui.view.*;
import com.vaadin.demo.ui.MainLayout;
import com.vaadin.demo.service.SourceService;

import java.util.HashMap;
import java.util.Set;
import jakarta.servlet.ServletConfig;
import jakarta.servlet.ServletException;
import com.vaadin.flow.di.Lookup;
import com.vaadin.flow.di.LookupInitializer;
import com.vaadin.flow.di.DefaultInstantiator;
import com.vaadin.flow.di.Instantiator;
import com.vaadin.flow.function.DeploymentConfiguration;
import com.vaadin.flow.server.ServiceException;
import com.vaadin.flow.server.VaadinServletService;
import com.vaadin.flow.router.InternalServerError;
import com.vaadin.flow.router.RouteNotFoundError;
import com.vaadin.flow.server.VaadinServlet;
import com.vaadin.flow.server.VaadinServletContext;
import com.vaadin.flow.server.startup.ErrorNavigationTargetInitializer;
import com.vaadin.flow.server.startup.RouteRegistryInitializer;
import com.vaadin.flow.server.startup.VaadinAppShellInitializer;
import com.vaadin.flow.server.startup.VaadinInitializerException;

/** Explicit bootstrap replaces classpath/annotation scanning on Android's DEX runtime. */
public final class OfficialDemoServlet extends VaadinServlet {
    @Override
    public void init(ServletConfig config) throws ServletException {
        VaadinServletContext context = new VaadinServletContext(config.getServletContext());
        if (context.getAttribute(Lookup.class) == null) {
            new LookupInitializer().initialize(context, new HashMap<>(),
                    lookup -> context.setAttribute(Lookup.class, lookup));
            try {
                new RouteRegistryInitializer().initialize(Set.of(MainLayout.class, DashboardView.class, ComponentsView.class, ProductsView.class, UsersView.class, SettingsView.class), context);
            } catch (VaadinInitializerException failure) {
                throw new ServletException("Cannot register the demo route", failure);
            }
            new ErrorNavigationTargetInitializer().initialize(
                    Set.of(RouteNotFoundError.class, InternalServerError.class), context);
            VaadinAppShellInitializer.init(Set.of(Application.class), context);
        }
        super.init(config);
    }

    /** Preserve upstream constructor injection without starting Spring on Android. */
    @Override
    protected VaadinServletService createServletService(DeploymentConfiguration configuration)
            throws ServiceException {
        VaadinServletService service = new VaadinServletService(this, configuration) {
            @Override
            protected java.util.concurrent.Executor createDefaultExecutor() {
                // Android has no virtual threads. The process owns this pool.
                return java.util.concurrent.ForkJoinPool.commonPool();
            }

            @Override
            protected Instantiator createInstantiator() {
                return new DefaultInstantiator(this) {
                    private final SourceService sources = new SourceService();

                    @Override
                    public <T> T getOrCreate(Class<T> type) {
                        if (type == DashboardView.class) return type.cast(new DashboardView(sources));
                        if (type == ComponentsView.class) return type.cast(new ComponentsView(sources));
                        if (type == ProductsView.class) return type.cast(new ProductsView(sources));
                        if (type == UsersView.class) return type.cast(new UsersView(sources));
                        if (type == SettingsView.class) return type.cast(new SettingsView(sources));
                        return super.getOrCreate(type);
                    }
                };
            }
        };
        service.init();
        return service;
    }
}
