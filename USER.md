# USER.md - Modelo de Usuario

Almacena las preferencias estables del usuario y datos de su perfil como directivas activas para guiar sesiones futuras.

Usa una directiva por entrada:

```md
<!-- observed: YYYY-MM-DD | status: active -->

- Prefer concise progress updates during implementation work.
```

- Inicia cada directiva con un imperativo como `Always`, `Never` o `Prefer`.
- Registra la fecha de observación y el estado (`active` o `superseded`) en la línea de metadatos.
- Cuando una preferencia cambie, marca la entrada anterior como `superseded` y reescribe la directiva activa en el lugar. Nunca agregues directivas activas contradictorias.
- Mantén aquí el estilo de comunicación estable, relaciones y contexto de proyectos activos. Registra hechos duraderos no relacionados con el perfil y decisiones clave en `MEMORIA.md`.
- Guarda este archivo en la raíz del espacio de trabajo como `USER.md`. Se carga en cada sesión con un presupuesto de 4,000 caracteres.

## Directivas

<!-- observed: 2026-10-19 | status: active -->

- Prefer respuestas concisas, estructuradas y directas al grano, sin rodeos corporativos ni introducciones innecesarias.

<!-- observed: 2026-10-19 | status: active -->

- Always mantener la seguridad Human-in-the-Loop pidiendo confirmación antes de modificar, borrar o acceder a rutas sensibles y bases de datos.

<!-- observed: 2026-10-27 | status: active -->

- Always alinear propuestas, contenidos y mensajes de prospección de Avril Lab con el ICP (Builders/founders técnicos en MX-LATAM) y las ofertas comerciales (Day Pass $6 USD / 48h, Trial $15 USD / 7d), asegurando siempre un Call To Action (CTA) claro.

<!-- observed: 2026-10-27 | status: active -->

- Prefer verificar hechos, fuentes externas y noticias mediante extracción directa con 'web_fetch' o 'web_search' en runtime.

## Relacionado

- [Espacio de trabajo del agente](/concepts/agent-workspace)
