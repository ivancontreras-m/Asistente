# Arnés de Marketing y Contenido — Avril Lab (C2)

> Ciclo 2 · Iván · Octubre 2026  
> Prototipo acotado y demostrable, NO sistema de producción.

## Descripción

Flujo agéntico reutilizable que recibe un briefing de marketing (oferta, audiencia, CTA), investiga hechos en la web, genera contenido de campaña para Avril Lab y lo deja listo para revisión humana. **No publica contenido automáticamente.**

### Pipeline de 4 etapas

```text
Briefing JSON
     |
     v
[1. Investigación web]
     |
     v
[2. Generación de contenido]
     |
     v
[3. Verificación de afirmaciones]
     |
     v
[4. Preparación de materiales]
     |
     v
Archivos Markdown + Reporte JSON
     |
     v
REVISIÓN Y APROBACIÓN HUMANA
```

1. **Investigación:** busca datos relevantes en la web con Brave Search / DuckDuckGo.
2. **Generación:** produce copy alineado al ICP y ofertas de Avril Lab.
3. **Fact-check:** verifica afirmaciones automáticamente y las clasifica (✅/⚠️/🔴).
4. **Salida:** guarda materiales `.md` con metadatos en `output_marketing/`.

El sistema de revisión clasifica las afirmaciones y determina la acción a seguir. Las condiciones comerciales y capacidades de Avril Lab se contrastan contra información autorizada, no solo búsqueda web genérica:

| Estado | Clasificación | Acción posterior del sistema |
|---|---|---|
| ✅ | Verificado | Conservar con fuente |
| ⚠️ | No confirmado | Marcar para revisión humana |
| 🔴 | Contradictorio | Retirar del copy propuesto |

## Instalación

```bash
# 1. Clonar el repositorio
git clone https://github.com/ivancontreras-m/Asistente.git
cd Asistente

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Configurar variables de entorno
cp .env.example .env
```

Editar `.env` con las variables correspondientes:

```env
NVIDIA_API_KEY=
BRAVE_API_KEY=
```

La clave de Brave es opcional; se utiliza DuckDuckGo como alternativa.

**Nota de seguridad:** El archivo `.env` está excluido del control de versiones mediante `.gitignore`. El archivo `.env.example` contiene únicamente los nombres de las variables requeridas, nunca credenciales reales. Los prompts internos están documentados directamente dentro de las funciones de `agente.py`.

### Dependencias

- Python 3.10+
- `openai>=1.0.0` (cliente NVIDIA NIM con base_url)
- `duckduckgo-search>=6.0.0` (fallback de búsqueda)
- `python-dotenv>=1.0.0`
- `python-docx>=1.0.0`
- `requests` (búsquedas web)
- `fastapi` + `uvicorn` (API REST)

## Ejecución

### Opción 1: CLI (recomendado para demo)

```bash
# Con el briefing de ejemplo (3 piezas)
python agente.py --marketing briefing_ejemplo.json

# Con el briefing de variación (1 pieza)
python agente.py --marketing briefing_variacion.json

# Crear tu propio archivo JSON (ej. mi_briefing.json) y ejecutarlo
python agente.py --marketing mi_briefing.json
```

### Opción 2: API REST

```bash
# 1. Iniciar servidor (Terminal 1)
python agente.py

# 2. POST a /marketing (Terminal 2)
# Windows (PowerShell):
Invoke-RestMethod -Uri http://127.0.0.1:8000/marketing -Method Post -ContentType "application/json" -Body '{"tipo_pieza":"post","tema":"Avril Lab para builders de IA","audiencia":"Builders y founders tecnicos en MX-LATAM","oferta":"Day Pass $6 USD/48h o Trial $15 USD/7d","cta":"Reserva tu seat en avrillab.com"}'

# Linux / macOS / Git Bash:
curl -X POST http://127.0.0.1:8000/marketing -H "Content-Type: application/json" -d '{"tipo_pieza":"post","tema":"Avril Lab para builders de IA","audiencia":"Builders y founders tecnicos en MX-LATAM","oferta":"Day Pass $6 USD/48h o Trial $15 USD/7d","cta":"Reserva tu seat en avrillab.com"}'

# O probar sin comandos desde el navegador (Swagger UI):
# http://127.0.0.1:8000/docs
```

### Opción 3: Chat interactivo

```bash
python agente.py --chat
```

Luego escribir:

"Genera contenido de marketing con el briefing en briefing_ejemplo.json"

## Entradas y Salidas

### Entrada: `briefing_ejemplo.json`

```json
{
  "piezas": [
    {
      "tipo_pieza": "post",
      "tema": "Experimentación con agentes IA",
      "audiencia": "Desarrolladores",
      "oferta": "Avril Lab",
      "cta": "Conoce Avril Lab",
      "contexto_extra": "Contenido informativo"
    }
  ]
}
```

*Nota: El archivo físico `briefing_ejemplo.json` en el repositorio incluye las 3 piezas completas.*

### Salida: `output_marketing/`

- `post_YYYYMMDD_HHMMSS.md` — Material generado con copy + fact-check + métricas.
- `carrusel_YYYYMMDD_HHMMSS.md` — Carrusel guionado de 5 slides.
- `guion_YYYYMMDD_HHMMSS.md` — Guion de video corto (60s).
- `reporte_ejecucion_YYYYMMDD_HHMMSS.json` — Reporte con métricas consolidadas.

Cada archivo `.md` incluye:

- Contenido generado.
- Reporte de fact-check con afirmaciones clasificadas.
- Métricas (llamadas LLM, búsquedas web, tokens, duración).
- Briefing utilizado.
- Aviso de "NO PUBLICADO — requiere revisión humana".

## Pruebas

### Prueba 1: Briefing de ejemplo (3 piezas)

```bash
python agente.py --marketing briefing_ejemplo.json
```

**Resultado esperado:** 3 archivos `.md` en `output_marketing/` + 1 reporte JSON.

### Prueba 2: Briefing personalizado (variación)

Crear un archivo `briefing_variacion.json` con diferente audiencia/tema/CTA y ejecutar:

```bash
python agente.py --marketing briefing_variacion.json
```

### Prueba 3: Pieza individual vía API

Iniciar el servidor (Terminal 1):

```bash
python agente.py
```

En otra terminal (Terminal 2):

```bash
# Windows (PowerShell):
Invoke-RestMethod -Uri http://127.0.0.1:8000/marketing -Method Post -ContentType "application/json" -Body '{"tipo_pieza":"post","tema":"Avril Lab para builders de IA","audiencia":"Builders y founders tecnicos en MX-LATAM","oferta":"Day Pass $6 USD/48h o Trial $15 USD/7d","cta":"Reserva tu seat en avrillab.com"}'

# Linux / macOS / Git Bash:
curl -X POST http://127.0.0.1:8000/marketing -H "Content-Type: application/json" -d '{"tipo_pieza":"post","tema":"Avril Lab para builders de IA","audiencia":"Builders y founders tecnicos en MX-LATAM","oferta":"Day Pass $6 USD/48h o Trial $15 USD/7d","cta":"Reserva tu seat en avrillab.com"}'
```

## Limitaciones

- **No publica automáticamente.** Todo el contenido queda en archivos locales.
- **Calidad del LLM.** Depende del modelo configurado en `MODELO_LLM`. Con modelos gratuitos (Nemotron) la calidad puede ser menor.
- **Fact-check automatizado no es infalible.** Clasifica afirmaciones, pero la revisión humana final es obligatoria.
- **Búsqueda web puede fallar.** Si Brave API y DuckDuckGo no están disponibles, la investigación se omite parcialmente.
- **Sin generación de imágenes.** Los carruseles solo incluyen texto guionado y notas de diseño, no imágenes.
- **Costos.** Cada ejecución completa (3 piezas) consume ~6 llamadas al LLM + ~9-12 búsquedas web.

## Costo y Tiempo Real de Ejecución (Pruebas C2)

Durante las pruebas documentadas de este ciclo, se registraron las siguientes métricas utilizando el modelo `nvidia/nemotron-3-ultra-550b-a55b` y el arnés de 4 etapas:

| Ejecución | Piezas | Tiempo Total | Tokens Estimados | Costo Registrado |
|---|---|---|---|---|
| Prueba 1 (Briefing Ejemplo) | 3 | 43.8 s | 15,575 | $0 USD (Free tier) |
| Prueba 2 (Briefing Variación) | 1 | 14.7 s | 4,925 | $0 USD (Free tier) |

*Nota: El arnés optimizó la latencia resolviendo cada pieza en un promedio de ~14-15 segundos, incluyendo la investigación web, generación y fact-checking.*

**▶️ Demo del Arnés en Ejecución:** [Ver video demostrativo](https://drive.google.com/file/d/1U1DDVzzheWnEPvxAj_XQvIR8o4aHonC9/view?usp=drive_link)

## Fallas Encontradas y Soluciones Aplicadas

### 1. Retorno de 0 caracteres en Nemotron (Free tier / Reasoning tokens)

**Falla:** Al invocar `nvidia/nemotron-3.5-lightning:free` en OpenRouter, el contenido generado devolvía un string vacío (0 caracteres) en las etapas de copy y fact-check.

**Posible causa técnica:** Los modelos de razonamiento y Mixture-of-Experts (MoE) de NVIDIA pueden emitir texto en el campo `reasoning` o `reasoning_content` en lugar del campo `content` (el cual puede quedar como `null`), o el proveedor de la capa gratuita puede experimentar timeouts intermitentes.

**Solución implementada:**

1. Se creó `extraer_texto_mensaje()` que examina en cascada `content`, `reasoning`, `reasoning_content`, `model_extra` y `model_dump()`.

2. Se creó `invocar_llm_robusto()` que cuenta con fallback en cascada dentro del ecosistema NVIDIA (`nvidia/nemotron-3-ultra-550b-a55b`, variantes free y router de respaldo) si el proveedor principal falla o devuelve 0 caracteres.

3. Se añadieron directivas estrictas de salida en los prompts para exigir texto Markdown plano y una función limpiadora `limpiar_wrappers_innecesarios()` para descartar wrappers o bloques JSON accidentales.

## Cambios Realizados

1. Añadida función `generar_contenido_marketing()` — pipeline de 4 etapas.
2. Añadida función `ejecutar_arnes_marketing()` — orquestador batch con reporte.
3. Implementadas las funciones `invocar_llm_robusto()`, `extraer_texto_mensaje()` y `limpiar_wrappers_innecesarios()` para blindar llamadas a LLMs de razonamiento.
4. Configurado por defecto el modelo `nvidia/nemotron-3-ultra-550b-a55b`.
5. Añadido modo CLI `--marketing` para ejecución desde terminal.
6. Añadidos endpoints `POST /marketing` y `POST /marketing/batch` en FastAPI.
7. Registradas nuevas herramientas en el sistema de function calling del agente.
8. Creado `briefing_ejemplo.json` con 3 piezas de demostración.
9. Añadido modelo Pydantic `BriefingMarketing` para validación de entrada.
10. Diccionario `HECHOS_VERIFICADOS_AVRIL` como fuente autoritativa de claims.

## Estructura del Proyecto

```text
Asistente/
├── agente.py                  # Agente principal con arnés de marketing
├── briefing_ejemplo.json      # Briefing de demo con 3 piezas
├── briefing_variacion.json    # Segunda prueba del arnés
├── requirements.txt           # Dependencias Python
├── .env.example               # Plantilla de variables de entorno
├── .env                       # API keys (no se sube a GitHub)
├── .gitignore
├── README.md                  # Este archivo
├── output_marketing/          # Materiales de marketing
│   ├── post_*.md
│   ├── carrusel_*.md
│   ├── guion_*.md
│   └── reporte_ejecucion_*.json
└── ...
```

## Evidencias de Entrega

- Código fuente (`agente.py`) y configuración del arnés (`requirements.txt`, `.env.example`).
- Entradas: `briefing_ejemplo.json` y `briefing_variacion.json`.
- Salidas: Tres materiales generados para Avril Lab y reportes JSON en la carpeta `output_marketing/`.
- Evidencia de verificación de afirmaciones dentro de los archivos `.md`.
- **Video demostrativo de ejecución:** [Ver demo del arnés](https://drive.google.com/file/d/1U1DDVzzheWnEPvxAj_XQvIR8o4aHonC9/view?usp=drive_link).

*Importante: Todos los materiales generados requieren aprobación humana antes de su publicación.*

## Licencia

Ciclo 2, Octubre 2026.