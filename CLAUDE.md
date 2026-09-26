# Fareas( Attendance System with facial recognition) - AI Assistant Guidelines

This project is built using **Angular v21.1.4**. Please follow these architectural and stylistic guidelines when contributing to the codebase.

## 🏗️ Code Scaffolding

Always use Angular CLI abbreviations to generate elements, specifying the exact route/path to maintain the folder structure (e.g., inside `core/`, `features/`, etc.):

- **Components:** `ng g c {path}/component-name`
- **Services:** `ng g s {path}/service-name`
- **Guards:** `ng g g {path}/guard-name`
- **Interceptors:** `ng g interceptor {path}/interceptor-name`
- **Pipes:** `ng g p {path}/pipe-name`

## 🎨 UI & Design Consistency

- **Global Styles:** Always check the `src/styles.css` file before adding new styles. Reuse CSS variables and global classes.
- **UI Persistence:** Maintain visual consistency across the entire application. The design must follow a minimalist, clean, and modern aesthetic (Vercel/Shadcn style).
- **CSS Scoped vs Global:** Use encapsulated styles within components only when strictly necessary, prioritizing global consistency.
- **Icons:** Iconify icons are being used. The syntax is `<iconify-icon icon="material-symbols:10k" width="20" />`.

## ⚙️ Architecture and Best Practices

- **Lazy Loading:** Strictly apply Lazy Loading techniques in routing (`loadComponent` or `loadChildren`) to optimize the initial bundle weight and improve performance.
- **Standalone Components:** In Angular 21, leverage standalone components to the fullest, avoiding the unnecessary creation of `NgModules`.
- **Modern Control Flow:** Use the new control flow syntax (`@if`, `@for`, `@switch`) instead of the old structural directives (`*ngIf`, `*ngFor`).
- **Signals:** Prioritize the use of Angular Signals for reactivity and state management over RxJS whenever possible.
- **Structure:** Respect the project division visible in the architecture (e.g., separating business logic in `core/` and views in `features/`).
