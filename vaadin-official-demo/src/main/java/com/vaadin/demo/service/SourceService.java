package com.vaadin.demo.service;

import java.io.IOException;
import java.nio.charset.StandardCharsets;

public class SourceService {

    public String getSource(Class<?> clazz) {
        String path = "source/" + clazz.getName().replace('.', '/') + ".java";
        try (var resource = getClass().getClassLoader().getResourceAsStream(path)) {
            if (resource == null) throw new IOException("Missing source: " + path);
            return new String(resource.readAllBytes(), StandardCharsets.UTF_8);
        } catch (IOException e) {
            return "// Source not available for " + clazz.getSimpleName() + "\n// Path: " + path;
        }
    }

    public String getGitHubUrl(Class<?> clazz) {
        String path = "src/main/java/" + clazz.getName().replace('.', '/') + ".java";
        return "https://github.com/vaadin/vaadin-demo/blob/main/" + path + "#L1";
    }
}
