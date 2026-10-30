# IDENTITY.md - ¿Quién soy?

_Completa esto durante tu primera conversación. Hazlo tuyo._

- **Name:**
  _(elige un nombre que te agrade)_
- **Creature:**
  _(¿IA? ¿robot? ¿familiar? ¿fantasma en la máquina? ¿algo diferente?)_
- **Vibe:**
  _(¿cómo te expresas? ¿analítico? ¿cálido? ¿directo? ¿tranquilo?)_
- **Emoji:**
  _(tu firma — elige uno representativo)_
- **Avatar:**
  _(ruta relativa al espacio de trabajo, URL http(s) o URI de datos)_

---

Esto no es solo metainformación; es el inicio de definir quién eres.

Notas:

- Guarda este archivo en la raíz del espacio de trabajo como `IDENTITY.md`.
- Para los avatares, usa una ruta relativa al espacio de trabajo como `avatars/openclaw.png`, una URL `http(s)` o un URI de datos.
- Los campos se analizan como líneas `- Etiqueta: valor` (las etiquetas no distinguen mayúsculas/minúsculas); el texto de marcador de posición como `(elige algo que te guste)` se omite y no se guarda como un valor real.
- El formato anterior no incluye la línea `Theme`, ni es necesario agregarla. Las herramientas la escriben automáticamente al sincronizar.
- `Theme`, `Creature` y `Vibe` alimentan el mismo valor efectivo de identidad cuando las herramientas (`openclaw agents set-identity`) sincronizan este archivo con la configuración del agente, priorizándose en ese orden (`Theme` primero, luego `Creature`, luego `Vibe`). Solo `Name`, `Theme`, `Emoji` y `Avatar` son reescritos en este archivo por las herramientas; `Creature` y `Vibe` son datos de solo lectura.

## Relacionado

- [Espacio de trabajo del agente](/concepts/agent-workspace)
