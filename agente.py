import os
import json
import inspect
import subprocess
import platform
import sqlite3
import threading
import requests
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from openai import OpenAI
try:
    from ddgs import DDGS
except ImportError:
    from duckduckgo_search import DDGS
import webbrowser
from html.parser import HTMLParser
from datetime import datetime

# Cargar variables de entorno desde .env si existe
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Configuración del cliente para NVIDIA NIM (Endpoint Gratuito)
api_key = os.getenv("NVIDIA_API_KEY") or "nvapi-placeholder"
client = OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key=api_key,
)

BRAVE_API_KEY = os.getenv("BRAVE_API_KEY")
print("BRAVE_API_KEY cargada:", bool(BRAVE_API_KEY))

AVRIL_MCP_URL = os.getenv("AVRIL_MCP_URL", "")
print("AVRIL_MCP_URL configurada:", bool(AVRIL_MCP_URL))

MODELO = os.getenv("MODELO_LLM", "nvidia/nemotron-3-ultra-550b-a55b")
ARCHIVO_MEMORIA = "MEMORIA.md"
MAX_ITERACIONES_HERRAMIENTAS = 15

# Inicialización de FastAPI y modelo de datos
app = FastAPI(title="Agente Inteligente API")

class Peticion(BaseModel):
    query: str

class BriefingMarketing(BaseModel):
    oferta: str = "Day Pass $6 USD/48h o Trial $15 USD/7d"
    audiencia: str = "Builders y founders técnicos en MX-LATAM"
    cta: str = "Reserva tu seat en avrillab.com"
    tipo_pieza: str = "post"
    tema: str = "Avril Lab para builders de IA"
    contexto_extra: str = ""

# --- ESTILOS DE COLOR EN TERMINAL ---
C_RESET = "\033[0m"
C_BOLD = "\033[1m"
C_USER = "\033[1;36m"     # Ciano
C_AGENT = "\033[1;32m"    # Verde
C_WARN = "\033[1;33m"     # Amarillo
C_ERROR = "\033[1;31m"    # Rojo
C_LINE = "\033[0;35m"     # Púrpura

RUTAS_SENSIBLES = [
    "/.ssh", "/.aws", "/.gnupg", "Library", "System", "Windows",
    "Program Files", "AppData", ".env", "id_rsa", "passwords"
]

def es_ruta_sensible(ruta):
    ruta_absoluta = os.path.abspath(ruta)
    for palabra_clave in RUTAS_SENSIBLES:
        if palabra_clave.lower() in ruta_absoluta.lower():
            return True, ruta_absoluta
    return False, ruta_absoluta

def cargar_memoria_contexto():
    if os.path.exists(ARCHIVO_MEMORIA):
        with open(ARCHIVO_MEMORIA, "r", encoding="utf-8") as f:
            return f.read().strip()
    return "No hay archivo de memoria previo."

def enviar_notificacion_sistema(titulo, mensaje, es_error=False):
    sistema = platform.system()
    try:
        if sistema == "Windows":
            def _mostrar_alerta_windows():
                try:
                    import ctypes
                    try:
                        import winsound
                        sonido = winsound.MB_ICONHAND if es_error else winsound.MB_ICONASTERISK
                        winsound.MessageBeep(sonido)
                    except Exception:
                        pass
                    # 0x40 = MB_ICONINFORMATION, 0x10 = MB_ICONHAND, 0x40000 = MB_TOPMOST (siempre al frente)
                    icono_estilo = (0x10 if es_error else 0x40) | 0x40000
                    ctypes.windll.user32.MessageBoxW(0, str(mensaje), str(titulo), icono_estilo)
                except Exception as ex_win:
                    # Respaldo por PowerShell si ctypes fallara
                    ps_cmd = f'Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.MessageBox]::Show("{mensaje}", "{titulo}")'
                    subprocess.Popen(["powershell", "-Command", ps_cmd])

            # Ejecutar en hilo secundario para no bloquear el agente
            threading.Thread(target=_mostrar_alerta_windows, daemon=True).start()

        elif sistema == "Darwin":  # macOS
            sonido = "Basso" if es_error else "Glass"
            command = f'display notification "{mensaje}" with title "{titulo}" sound name "{sonido}"'
            subprocess.run(["osascript", "-e", command])
        else:  # Linux
            subprocess.Popen(["notify-send", titulo, mensaje])
    except Exception as e:
        print(f"{C_ERROR}(Error enviando notificación: {e}){C_RESET}")

def solicitar_confirmacion_humana(accion, detalles):
    enviar_notificacion_sistema(
        "🔒 Permiso Requerido por el Agente",
        f"Acción sensible: {accion}. Revisa la terminal.",
        es_error=False
    )
    
    print("\n" + f"{C_WARN}⚠️  "*15)
    print("🔒 [ALERTA DE SEGURIDAD - ACCIÓN SENSIBLE DETECTADA]")
    print(f"👉 Acción solicitada: {accion}")
    print(f"📝 Detalles: {detalles}")
    print("⚠️  "*15 + f"{C_RESET}")
    
    try:
        respuesta = input(f"{C_BOLD}¿Autorizas la ejecución de esta acción? (s/n): {C_RESET}").strip().lower()
        return respuesta in ['s', 'si', 'y', 'yes']
    except (KeyboardInterrupt, EOFError):
        return False

# --- HERRAMIENTAS FUNDAMENTALES ---

def ejecutar_comando_terminal(comando):
    """Herramienta 1: Ejecutor de comandos de terminal controlado"""
    if solicitar_confirmacion_humana("Ejecutar comando de terminal", f"Comando: '{comando}'"):
        try:
            resultado = subprocess.run(
                comando, shell=True, capture_output=True, text=True, timeout=60
            )
            salida = resultado.stdout if resultado.stdout else resultado.stderr
            return f"Salida del comando (Código {resultado.returncode}):\n{salida}"
        except Exception as e:
            return f"Error ejecutando comando: {str(e)}"
    else:
        return "Denegado: El usuario rechazó la ejecución del comando en la terminal."

class SimpleHTMLTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.result = []
        self.skip = False

    def handle_starttag(self, tag, attrs):
        if tag.lower() in ('script', 'style', 'noscript', 'header', 'footer', 'nav', 'svg'):
            self.skip = True

    def handle_endtag(self, tag):
        if tag.lower() in ('script', 'style', 'noscript', 'header', 'footer', 'nav', 'svg'):
            self.skip = False

    def handle_data(self, data):
        if not self.skip and data.strip():
            self.result.append(data.strip())

def web_search(query=None, consulta=None, count=5, country=None, language=None, freshness=None):
    """Busca en la web en tiempo real utilizando Brave Search API con fallback seguro en DDGS."""
    texto_busqueda = query if query is not None else consulta
    if not texto_busqueda:
        return "Error: No se proporcionó ninguna consulta para buscar."

    # 1. Lógica principal: Brave Search API
    try:
        if not BRAVE_API_KEY:
            raise ValueError("No se encontró la variable BRAVE_API_KEY configurada en el entorno.")

        url = "https://api.search.brave.com/res/v1/web/search"
        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": BRAVE_API_KEY,
        }
        params = {
            "q": texto_busqueda,
            "count": count or 5,
        }
        if country:
            params["country"] = country
        if language:
            params["search_lang"] = language
        if freshness:
            params["freshness"] = freshness

        respuesta = requests.get(url, headers=headers, params=params, timeout=10)
        respuesta.raise_for_status()
        datos = respuesta.json()

        resultados = datos.get("web", {}).get("results", [])
        if not resultados:
            return "No se encontraron resultados relevantes en la web."

        formateado = []
        for r in resultados:
            titulo = r.get("title", "Sin título")
            link = r.get("url", "")
            descripcion = r.get("description", "")
            formateado.append(f"📌 Título: {titulo}\n🔗 URL: {link}\n📄 Contenido: {descripcion}\n")
        return "\n---\n".join(formateado)

    except Exception as e_brave:
        # 2. Lógica de respaldo: DDGS con context manager seguro y manejo de compatibilidad
        print(f"{C_WARN}⚠️ [Brave Search no disponible/falló ({e_brave}) -> Activando respaldo seguro con DDGS...]{C_RESET}")
        try:
            with DDGS() as ddgs:
                try:
                    results = list(ddgs.text(keywords=texto_busqueda, max_results=count or 5))
                except TypeError:
                    results = list(ddgs.text(texto_busqueda, max_results=count or 5))

            if not results:
                return "No se encontraron resultados relevantes en la web."

            formateado = []
            for r in results:
                formateado.append(f"📌 Título: {r.get('title')}\n🔗 URL: {r.get('href')}\n📄 Contenido: {r.get('body')}\n")
            return "\n---\n".join(formateado)
        except Exception as e:
            return f"Error técnico al ejecutar la búsqueda web: {str(e)}"

# Alias de compatibilidad hacia atrás
buscar_en_web = web_search

def web_fetch(url, max_chars=4000):
    """Extrae el contenido de texto legible de una página web a partir de su URL."""
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        resp = requests.get(url, headers=headers, timeout=12)
        resp.raise_for_status()

        content_type = resp.headers.get("Content-Type", "").lower()
        if "json" in content_type:
            return resp.text[:max_chars]

        parser = SimpleHTMLTextExtractor()
        parser.feed(resp.text)
        texto = " ".join(parser.result)
        if not texto:
            texto = resp.text[:max_chars]
        else:
            texto = " ".join(texto.split())
            if len(texto) > max_chars:
                texto = texto[:max_chars] + f"\n... [Contenido truncado a {max_chars} caracteres]"
        return f"Contenido extraído de '{url}':\n\n{texto}"
    except Exception as e:
        return f"Error al obtener contenido de '{url}': {str(e)}"

def abrir_url_en_navegador(url):
    """Abre una URL web directamente en el navegador predeterminado del sistema."""
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url
    try:
        webbrowser.open(url)
        return f"Éxito: Se abrió en el navegador la URL '{url}'."
    except Exception as e:
        return f"Error al abrir navegador: {str(e)}"

# Alias de compatibilidad
browser = abrir_url_en_navegador

def consultar_mcp_avril_knowledge(accion="get_current_state", namespace="canonical", query=""):
    """Consulta directa al MCP avril-knowledge (base de conocimiento y estado autoritativo de Avril Systems).
    Acciones soportadas: 'list_namespaces', 'get_current_state', 'get_decision', 'query_knowledge'.
    Namespaces: 'canonical', 'research', 'current-state', 'sources', 'glossary'."""
    # 1. Conexión HTTP/JSON-RPC si hay servidor MCP configurado en red o túnel
    if AVRIL_MCP_URL:
        try:
            payload = {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": accion,
                    "arguments": {
                        "namespace": namespace,
                        "query": query
                    }
                },
                "id": 1
            }
            resp = requests.post(AVRIL_MCP_URL, json=payload, timeout=10)
            resp.raise_for_status()
            return f"Respuesta MCP avril-knowledge:\n{json.dumps(resp.json(), indent=2, ensure_ascii=False)}"
        except Exception as e:
            return f"Error al consultar endpoint MCP avril-knowledge ({AVRIL_MCP_URL}): {str(e)}"

    # 2. Respaldo local de contexto/corpus si no hay servidor MCP remoto activo
    if accion == "list_namespaces":
        return "Namespaces disponibles en MCP avril-knowledge: ['canonical', 'research', 'current-state', 'sources', 'glossary']. (Servidor remoto offline; configure AVRIL_MCP_URL en .env para enlace en tiempo real)."

    archivos_relevantes = ["MEMORIA.md", "DREAMS.md", "IDENTITY.md"]
    detalles = []
    for arch in archivos_relevantes:
        if os.path.exists(arch):
            try:
                with open(arch, "r", encoding="utf-8") as f:
                    contenido = f.read()
                    if query and query.lower() in contenido.lower():
                        detalles.append(f"--- Coincidencia en {arch} ---\n{contenido[:600]}")
            except Exception:
                pass

    if accion == "get_current_state":
        if detalles:
            return "Estado autoritativo de Avril Systems (Corpus local):\n" + "\n".join(detalles)
        return "Estado actual: Sistema activo localmente. Servidor MCP remoto no configurado (puedes definir AVRIL_MCP_URL en .env para enlace remoto)."
    elif accion == "get_decision":
        if detalles:
            return "Decisiones encontradas en corpus local:\n" + "\n".join(detalles)
        return "ADR / Decisiones de Arquitectura: Ver registros de estado en MEMORIA.md o activar servidor MCP remoto en AVRIL_MCP_URL."
    else:
        if detalles:
            return f"Resultados para '{query}' en corpus avril-knowledge local:\n" + "\n".join(detalles)
        return f"MCP avril-knowledge: Sin servidor remoto en AVRIL_MCP_URL ni coincidencias locales para '{query}'."

@app.post("/buscar")
def buscar(peticion: Peticion):
    """Endpoint para ejecutar búsquedas web usando Brave Search con fallback a DuckDuckGo."""
    try:
        texto_de_la_busqueda = web_search(query=peticion.query)
        return {"resultado": texto_de_la_busqueda}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/marketing")
def endpoint_marketing(briefing: BriefingMarketing):
    """Endpoint del arnés de marketing: genera contenido para Avril Lab a partir de un briefing."""
    try:
        resultado = generar_contenido_marketing(briefing.model_dump())
        return json.loads(resultado)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/marketing/batch")
def endpoint_marketing_batch(piezas: list[BriefingMarketing]):
    """Endpoint batch: genera múltiples piezas de marketing a partir de una lista de briefings."""
    try:
        resultados = []
        for pieza in piezas:
            resultado = generar_contenido_marketing(pieza.model_dump())
            resultados.append(json.loads(resultado))
        return {"resultados": resultados, "total": len(resultados)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def consultar_base_datos_sqlite(ruta_db, query_sql):
    """Herramienta 3: Consultor de base de datos local SQLite"""
    sensible, ruta_abs = es_ruta_sensible(ruta_db)
    if sensible:
        if not solicitar_confirmacion_humana("Acceso a BD Sensible", f"Ruta: '{ruta_abs}'"):
            return "Denegado: El usuario rechazó el acceso a la base de datos."

    try:
        conn = sqlite3.connect(ruta_abs)
        cursor = conn.cursor()
        cursor.execute(query_sql)
        
        if query_sql.strip().lower().startswith("select"):
            registros = cursor.fetchall()
            columnas = [desc[0] for desc in cursor.description] if cursor.description else []
            conn.close()
            encabezado = " | ".join(columnas)
            return f"Resultado SQL ({len(registros)} filas) [Columnas: {encabezado}]:\n{registros}"
        else:
            if solicitar_confirmacion_humana("Modificar Base de Datos SQL", f"Query: '{query_sql}'"):
                conn.commit()
                filas_afectadas = cursor.rowcount
                conn.close()
                return f"Éxito: Consulta ejecutada. Filas afectadas: {filas_afectadas}"
            else:
                conn.close()
                return "Denegado: El usuario canceló la modificación de la base de datos."
    except Exception as e:
        return f"Error en la base de datos SQL: {str(e)}"

def listar_archivos_carpeta(ruta_dir="."):
    """Lista archivos y directorios en la ruta especificada."""
    sensible, ruta_abs = es_ruta_sensible(ruta_dir)
    if sensible:
        if not solicitar_confirmacion_humana("Explorar carpeta sensible", f"Ruta: '{ruta_abs}'"):
            return "Denegado: El usuario rechazó el acceso."
    try:
        if os.path.exists(ruta_abs) and os.path.isdir(ruta_abs):
            archivos = sorted(os.listdir(ruta_abs))
            items = []
            for item in archivos[:60]:
                full = os.path.join(ruta_abs, item)
                tipo = "[DIR]" if os.path.isdir(full) else "[ARC]"
                items.append(f"{tipo} {item}")
            return f"Contenido de '{ruta_abs}':\n" + "\n".join(items)
        return f"Error: La carpeta '{ruta_abs}' no existe."
    except Exception as e:
        return f"Error al acceder al directorio: {str(e)}"

def buscar_archivos(nombre, directorio="."):
    """Busca archivos recursivamente por coincidencia de nombre."""
    ruta_abs = os.path.abspath(directorio)
    nombre_lower = nombre.lower()
    encontrados = []
    try:
        for raiz, dirs, archivos in os.walk(ruta_abs):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for archivo in archivos:
                if nombre_lower in archivo.lower():
                    encontrados.append(os.path.join(raiz, archivo))
            if len(encontrados) >= 40:
                break
        if not encontrados:
            return f"No se encontró ningún archivo con patrón '{nombre}' en '{ruta_abs}'."
        return f"Archivos encontrados ({len(encontrados)}):\n" + "\n".join(f"- {f}" for f in encontrados)
    except Exception as e:
        return f"Error buscando archivos: {str(e)}"

def leer_archivo_local(ruta):
    """Lee el contenido de un archivo de texto, código, o documentos .docx de Word."""
    sensible, ruta_abs = es_ruta_sensible(ruta)
    if sensible:
        if not solicitar_confirmacion_humana("Leer archivo sensible", f"Ruta: '{ruta_abs}'"):
            return "Denegado: El usuario rechazó la lectura."
    try:
        if not os.path.exists(ruta_abs):
            return f"Error: El archivo '{ruta_abs}' no existe."

        ext = os.path.splitext(ruta_abs)[1].lower()

        # Soporte completo para lectura de Word (.docx)
        if ext == ".docx":
            try:
                from docx import Document
                doc = Document(ruta_abs)
                parrafos = [p.text for p in doc.paragraphs if p.text.strip()]
                if not parrafos:
                    return f"El archivo Word '{os.path.basename(ruta_abs)}' está vacío o solo contiene imágenes/tablas."
                return f"Contenido extraído de Word ('{ruta_abs}'):\n" + "\n".join(parrafos)
            except ImportError:
                return "Error: python-docx no está instalado. Ejecuta: pip install python-docx"
            except Exception as docx_err:
                return f"Error al procesar archivo Word .docx: {str(docx_err)}"

        # Lectura de texto plano / código
        try:
            with open(ruta_abs, "r", encoding="utf-8") as f:
                return f"Contenido de '{ruta_abs}':\n{f.read()}"
        except UnicodeDecodeError:
            with open(ruta_abs, "r", encoding="latin-1") as f:
                return f"Contenido de '{ruta_abs}' (latin-1):\n{f.read()}"
    except Exception as e:
        return f"Error al leer archivo: {str(e)}"

def modificar_archivo_local(ruta, contenido):
    """Crea o modifica un archivo en cualquier directorio. Sin límites de extensión ni longitud."""
    _, ruta_abs = es_ruta_sensible(ruta)
    if solicitar_confirmacion_humana("Modificar/Crear archivo", f"Ruta: '{ruta_abs}'"):
        try:
            directorio = os.path.dirname(ruta_abs)
            if directorio:
                os.makedirs(directorio, exist_ok=True)
            with open(ruta_abs, "w", encoding="utf-8") as f:
                f.write(contenido)
            return f"Éxito: Archivo '{ruta_abs}' modificado/creado correctamente ({len(contenido)} caracteres)."
        except Exception as e:
            return f"Error al escribir archivo: {str(e)}"
    else:
        return "Denegado: El usuario rechazó modificar el archivo."

def abrir_archivo_en_sistema(ruta):
    """Abre un archivo físicamente en la pantalla con su aplicación nativa predeterminada."""
    _, ruta_abs = es_ruta_sensible(ruta)
    try:
        if os.path.exists(ruta_abs):
            sistema = platform.system()
            if sistema == "Darwin":
                subprocess.Popen(["open", ruta_abs])
            elif sistema == "Windows":
                os.startfile(ruta_abs)
            else:
                subprocess.Popen(["xdg-open", ruta_abs])
            return f"Éxito: Se abrió en pantalla el archivo '{ruta_abs}'."
        return f"Error: El archivo '{ruta_abs}' no fue encontrado."
    except Exception as e:
        return f"Error al abrir el archivo: {str(e)}"

# --- ARNÉS DE MARKETING Y CONTENIDO (C2 · Avril Lab) ---

DIRECTORIO_OUTPUT_MARKETING = "output_marketing"

HECHOS_VERIFICADOS_AVRIL = {
    "day_pass_precio": "$6 USD por 48 horas de acceso a un seat alojado/hosted",
    "trial_precio": "$15 USD por 7 días de acceso continuo",
    "producto": "Avril Lab — sandbox hosted para testing de agentes de IA e integraciones MCP",
    "icp": "Builders, founders y perfiles técnicos en México y Latinoamérica (MX-LATAM)",
}

def extraer_texto_mensaje(msg):
    """Extrae texto de un mensaje del LLM, buscando primero en 'content'
    y cayendo en 'reasoning', 'reasoning_content' o 'thinking' si 'content' está vacío."""
    if msg is None:
        return ""

    # 1. Intentar campo content directo
    contenido = getattr(msg, "content", None)
    if contenido and isinstance(contenido, str) and contenido.strip():
        # Si tiene tags <think>...</think>, extraer la respuesta final si existe
        if "</think>" in contenido:
            partes = contenido.split("</think>", 1)
            if len(partes) > 1 and partes[1].strip():
                return partes[1].strip()
        return contenido.strip()

    # 2. Atributos directos en el objeto (OpenRouter / vLLM / NVIDIA Nemotron)
    for attr in ("reasoning", "reasoning_content", "thought", "thinking"):
        val = getattr(msg, attr, None)
        if val and isinstance(val, str) and val.strip():
            return val.strip()

    # 3. model_extra (en Pydantic v2 donde OpenRouter envía campos fuera de la spec de OpenAI)
    if hasattr(msg, "model_extra") and isinstance(msg.model_extra, dict):
        for key in ("reasoning", "reasoning_content", "thought", "thinking"):
            val = msg.model_extra.get(key)
            if val and isinstance(val, str) and val.strip():
                return val.strip()

    # 4. model_dump() como respaldo exhaustivo
    try:
        dump = msg.model_dump() if hasattr(msg, "model_dump") else {}
        for key in ("reasoning", "reasoning_content", "thought", "thinking", "content"):
            val = dump.get(key)
            if val and isinstance(val, str) and val.strip():
                return val.strip()
    except Exception:
        pass

    return ""

def limpiar_wrappers_innecesarios(texto):
    """Elimina wrappers de formato innecesarios (json o markdown fences)
    para asegurar texto plano directamente."""
    if not texto:
        return ""
    t = texto.strip()

    # Eliminar bloques de código markdown si envuelven toda la respuesta
    if t.startswith("```") and t.endswith("```"):
        lineas = t.splitlines()
        if len(lineas) >= 2:
            primera = lineas[0].strip().lower()
            if primera in ("```json", "```markdown", "```md", "```text", "```txt", "```"):
                t = "\n".join(lineas[1:-1]).strip()

    # Si por error el LLM devolvió un JSON {"copy": "..."} o similar
    if t.startswith("{") and t.endswith("}"):
        try:
            datos = json.loads(t)
            if isinstance(datos, dict):
                for clave in ("contenido", "copy", "texto", "text", "content", "resultado", "respuesta", "material"):
                    if clave in datos and isinstance(datos[clave], str) and datos[clave].strip():
                        return datos[clave].strip()
        except Exception:
            pass

    return t

def invocar_llm_robusto(messages, temperature=0.7, max_tokens=2000, modelo_principal=None):
    """Llama al LLM extrayendo texto tanto de content como de reasoning/reasoning_content.
    Si el modelo devuelve 0 caracteres o falla, intenta con modelos de fallback dentro del
    ecosistema de NVIDIA y routers de respaldo."""
    modelo_a_usar = modelo_principal or MODELO
    candidatos = [
        modelo_a_usar,
        "nvidia/nemotron-3-ultra-550b-a55b:free",
        "nvidia/nemotron-3-ultra-550b-a55b",
        "nvidia/nemotron-3.5-super-vl:free",
        "nvidia/nemotron-3.5-lightning:free",
        "openrouter/free"
    ]
    # Lista única preservando orden
    modelos_a_probar = []
    for m in candidatos:
        if m and m not in modelos_a_probar:
            modelos_a_probar.append(m)

    ultimo_error = None
    tokens_usados = 0

    for m in modelos_a_probar:
        try:
            print(f"  🤖 Consultando LLM ({m})...")
            resp = client.chat.completions.create(
                model=m,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
            if hasattr(resp, "usage") and resp.usage:
                tokens_usados += (getattr(resp.usage, "prompt_tokens", 0) or 0) + (getattr(resp.usage, "completion_tokens", 0) or 0)

            msg = resp.choices[0].message
            texto = extraer_texto_mensaje(msg)
            texto = limpiar_wrappers_innecesarios(texto)

            if texto and len(texto.strip()) > 0:
                return texto, tokens_usados, m
            else:
                print(f"  {C_WARN}⚠️ {m} devolvió respuesta vacía (0 caracteres). Probando siguiente modelo...{C_RESET}")
        except Exception as e:
            ultimo_error = e
            print(f"  {C_WARN}⚠️ Fallo en llamada a {m}: {e}. Probando siguiente modelo...{C_RESET}")

    raise RuntimeError(f"Todos los modelos de LLM fallaron o devolvieron 0 caracteres. Último error: {ultimo_error}")


def generar_contenido_marketing(briefing_json):
    """Arnés de marketing C2: pipeline briefing → investigación → copy → fact-check → materiales.

    Recibe un briefing JSON (string o dict) con: oferta, audiencia, cta, tipo_pieza, tema, contexto_extra.
    Retorna JSON con la pieza generada, fact-check, rutas y métricas.
    No publica nada automáticamente; todo queda en archivos locales para revisión humana."""

    inicio = datetime.now()
    metricas = {"llamadas_llm": 0, "busquedas_web": 0, "tokens_estimados": 0}

    # --- Parse briefing ---
    if isinstance(briefing_json, str):
        try:
            briefing = json.loads(briefing_json)
        except json.JSONDecodeError:
            return json.dumps({"error": "El briefing no es un JSON válido."}, ensure_ascii=False)
    else:
        briefing = briefing_json

    oferta = briefing.get("oferta", HECHOS_VERIFICADOS_AVRIL["day_pass_precio"] + " o " + HECHOS_VERIFICADOS_AVRIL["trial_precio"])
    audiencia = briefing.get("audiencia", HECHOS_VERIFICADOS_AVRIL["icp"])
    cta = briefing.get("cta", "Reserva tu seat en avrillab.com")
    tipo_pieza = briefing.get("tipo_pieza", "post")
    tema = briefing.get("tema", "Avril Lab para builders de IA")
    contexto_extra = briefing.get("contexto_extra", "")

    print(f"\n{C_LINE}{'═'*60}")
    print(f"🚀 ARNÉS DE MARKETING AVRIL LAB — Pipeline iniciado")
    print(f"{'═'*60}{C_RESET}")
    print(f"  📋 Tipo: {tipo_pieza} | Tema: {tema}")
    print(f"  👥 Audiencia: {audiencia}")
    print(f"  💰 Oferta: {oferta}")
    print(f"  📢 CTA: {cta}\n")

    # ═══════════════════════════════════════
    # ETAPA 1: INVESTIGACIÓN WEB
    # ═══════════════════════════════════════
    print(f"{C_WARN}📡 [Etapa 1/4] Investigación web...{C_RESET}")

    queries_investigacion = [
        f"{tema} AI agents sandbox testing {datetime.now().year}",
        f"Avril Lab sandbox hosted AI MCP",
        f"{audiencia} herramientas agentes IA necesidades",
    ]
    if contexto_extra:
        queries_investigacion.append(contexto_extra)

    resultados_investigacion = []
    for q in queries_investigacion:
        print(f"  🔍 Buscando: {q}")
        try:
            resultado = web_search(query=q, count=3)
            resultados_investigacion.append(f"### Búsqueda: '{q}'\n{resultado}")
            metricas["busquedas_web"] += 1
        except Exception as e:
            resultados_investigacion.append(f"### Búsqueda: '{q}'\n⚠️ Error: {e}")

    investigacion_compilada = "\n\n---\n\n".join(resultados_investigacion)
    print(f"{C_AGENT}  ✅ Investigación completada ({metricas['busquedas_web']} búsquedas){C_RESET}\n")

    # ═══════════════════════════════════════
    # ETAPA 2: GENERACIÓN DE COPY
    # ═══════════════════════════════════════
    print(f"{C_WARN}✍️  [Etapa 2/4] Generación de copy ({tipo_pieza})...{C_RESET}")

    instrucciones_tipo = {
        "post": (
            "Genera un post para LinkedIn/redes profesionales de 150-280 palabras.\n"
            "Estructura: gancho inicial impactante → problema que resuelve → beneficio concreto → CTA.\n"
            "Usa emojis con moderación (máximo 3-4). Incluye 2-3 hashtags relevantes al final."
        ),
        "carrusel": (
            "Genera un carrusel guionado de 5 slides para redes sociales.\n"
            "Estructura por slide:\n"
            "  Slide 1: Gancho / pregunta provocadora\n"
            "  Slide 2: Problema que enfrenta la audiencia\n"
            "  Slide 3: Solución (Avril Lab) con dato concreto\n"
            "  Slide 4: Beneficio tangible / caso de uso\n"
            "  Slide 5: CTA claro con oferta\n"
            "Para cada slide incluye: [TEXTO PRINCIPAL] (máx 30 palabras) y [NOTA DE DISEÑO] (sugerencia visual)."
        ),
        "guion": (
            "Genera un guion para video corto de 60 segundos.\n"
            "Estructura:\n"
            "  [0-10s] GANCHO: pregunta o afirmación que detiene el scroll\n"
            "  [10-25s] PROBLEMA: dolor del builder/founder\n"
            "  [25-45s] SOLUCIÓN: cómo Avril Lab lo resuelve, con detalle concreto\n"
            "  [45-55s] PRUEBA SOCIAL o dato verificable\n"
            "  [55-60s] CTA directo con oferta\n"
            "Incluye indicaciones de tono, ritmo y elementos visuales sugeridos."
        ),
    }

    instruccion_pieza = instrucciones_tipo.get(tipo_pieza, instrucciones_tipo["post"])

    prompt_copywriting = f"""Eres un copywriter B2B especializado en marketing para startups de tecnología en Latinoamérica.

PRODUCTO: Avril Lab — sandbox hosted para testing de agentes de IA e integraciones MCP.
AUDIENCIA: {audiencia}
OFERTA COMERCIAL: {oferta}
CTA REQUERIDO: {cta}

INVESTIGACIÓN PREVIA (datos reales encontrados):
{investigacion_compilada[:3000]}

HECHOS VERIFICADOS DE AVRIL LAB (usa SOLO estos como fuente autorizada del producto):
- Precio Day Pass: {HECHOS_VERIFICADOS_AVRIL['day_pass_precio']}
- Precio Trial: {HECHOS_VERIFICADOS_AVRIL['trial_precio']}
- Producto: {HECHOS_VERIFICADOS_AVRIL['producto']}
- ICP: {HECHOS_VERIFICADOS_AVRIL['icp']}

REGLAS ESTRICTAS:
1. NO hagas afirmaciones de seguridad, ahorro, rendimiento o capacidades que NO estén en los hechos verificados.
2. NO inventes estadísticas, porcentajes ni datos numéricos sin fuente.
3. Si mencionas un dato externo, márcalo como [DATO: fuente].
4. El tono debe ser técnico pero accesible, directo, sin jerga corporativa vacía.
5. Este contenido es para REVISIÓN HUMANA, no se publicará automáticamente.

FORMATO DE SALIDA OBLIGATORIO:
- Responde DIRECTAMENTE con el texto del material en formato Markdown limpio y legible.
- NO uses JSON, NO envíes bloques de código ```json ni diccionarios estructurados.
- NO agregues introducciones conversacionales (como "Aquí tienes el post:"). Comienza de inmediato con el título o gancho de la pieza.

INSTRUCCIONES ESPECÍFICAS PARA ESTE TIPO DE PIEZA:
{instruccion_pieza}

TEMA: {tema}
{f'CONTEXTO ADICIONAL: {contexto_extra}' if contexto_extra else ''}

Genera el contenido ahora en Markdown plano:"""

    try:
        mensajes_copy = [
            {"role": "system", "content": "Eres un copywriter experto en marketing B2B para startups tech en LATAM. Generas contenido preciso, verificable y con CTA claro. Respondes en español, directamente en texto plano Markdown sin formato JSON."},
            {"role": "user", "content": prompt_copywriting}
        ]
        copy_generado, tokens_copy, modelo_usado_copy = invocar_llm_robusto(
            messages=mensajes_copy,
            temperature=0.7,
            max_tokens=2000,
            modelo_principal=MODELO
        )
        metricas["llamadas_llm"] += 1
        metricas["tokens_estimados"] += tokens_copy
        print(f"{C_AGENT}  ✅ Copy generado con {modelo_usado_copy} ({len(copy_generado)} caracteres){C_RESET}\n")
    except Exception as e:
        return json.dumps({"error": f"Error generando copy: {e}"}, ensure_ascii=False)

    # ═══════════════════════════════════════
    # ETAPA 3: FACT-CHECK AUTOMATIZADO
    # ═══════════════════════════════════════
    print(f"{C_WARN}🔍 [Etapa 3/4] Verificación de hechos (fact-check)...{C_RESET}")

    prompt_factcheck = f"""Eres un verificador de hechos (fact-checker) riguroso para contenido de marketing.

Analiza el siguiente contenido generado y realiza estas tareas:

1. EXTRAE todas las afirmaciones factuales (datos, precios, capacidades, comparaciones, estadísticas).
2. CLASIFICA cada afirmación:
   - ✅ VERIFICADA: coincide con los hechos conocidos o la investigación
   - ⚠️ NO VERIFICADA: no tiene respaldo en las fuentes disponibles
   - 🔴 CLAIM RIESGOSO: afirmación de seguridad, ahorro o capacidad no comprobada que debe eliminarse
3. GENERA un veredicto final: APROBADO / REQUIERE AJUSTES / RECHAZADO

FORMATO DE SALIDA OBLIGATORIO:
- Responde DIRECTAMENTE con el reporte en formato Markdown estructurado con viñetas.
- NO uses formato JSON ni bloques de código ```json.
- NO incluyas introducciones ni notas meta.

CONTENIDO A VERIFICAR:
---
{copy_generado}
---

HECHOS CONOCIDOS DE AVRIL LAB (fuente autoritativa):
- Producto: {HECHOS_VERIFICADOS_AVRIL['producto']}
- Day Pass: {HECHOS_VERIFICADOS_AVRIL['day_pass_precio']}
- Trial: {HECHOS_VERIFICADOS_AVRIL['trial_precio']}
- ICP: {HECHOS_VERIFICADOS_AVRIL['icp']}

INVESTIGACIÓN WEB DE REFERENCIA:
{investigacion_compilada[:2000]}

Reporte de fact-check estructurado en Markdown:"""

    try:
        mensajes_fc = [
            {"role": "system", "content": "Eres un fact-checker riguroso para marketing. Nunca apruebes afirmaciones sin evidencia. Respondes en español directamente en Markdown estructurado, sin wrappers JSON."},
            {"role": "user", "content": prompt_factcheck}
        ]
        factcheck_resultado, tokens_fc, modelo_usado_fc = invocar_llm_robusto(
            messages=mensajes_fc,
            temperature=0.1,
            max_tokens=1500,
            modelo_principal=MODELO
        )
        metricas["llamadas_llm"] += 1
        metricas["tokens_estimados"] += tokens_fc
        print(f"{C_AGENT}  ✅ Fact-check completado con {modelo_usado_fc}{C_RESET}\n")
    except Exception as e:
        factcheck_resultado = f"⚠️ Error en fact-check automático: {e}. REVISIÓN HUMANA OBLIGATORIA."

    # ═══════════════════════════════════════
    # ETAPA 4: GUARDAR MATERIALES
    # ═══════════════════════════════════════
    print(f"{C_WARN}💾 [Etapa 4/4] Guardando materiales...{C_RESET}")

    duracion = (datetime.now() - inicio).total_seconds()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    nombre_archivo = f"{tipo_pieza}_{timestamp}.md"

    os.makedirs(DIRECTORIO_OUTPUT_MARKETING, exist_ok=True)
    ruta_salida = os.path.join(DIRECTORIO_OUTPUT_MARKETING, nombre_archivo)

    contenido_archivo = f"""# Material de Marketing — Avril Lab
## {tipo_pieza.upper()}: {tema}

**Generado:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
**Audiencia:** {audiencia}
**Oferta:** {oferta}
**CTA:** {cta}
**Modelo LLM:** {MODELO}
**Estado:** 🟡 PENDIENTE DE REVISIÓN HUMANA

---

## 📝 Contenido Generado

{copy_generado}

---

## 🔍 Reporte de Fact-Check

{factcheck_resultado}

---

## 📊 Métricas de Ejecución

- Llamadas al LLM: {metricas['llamadas_llm']}
- Búsquedas web: {metricas['busquedas_web']}
- Tokens estimados: {metricas['tokens_estimados']}
- Duración: {duracion:.1f} segundos

---

## 📋 Briefing Utilizado

```json
{json.dumps(briefing, indent=2, ensure_ascii=False)}
```

---

> ⚠️ **ESTE MATERIAL NO HA SIDO PUBLICADO.** Requiere revisión y aprobación humana antes de cualquier uso.
"""

    try:
        with open(ruta_salida, "w", encoding="utf-8") as f:
            f.write(contenido_archivo)
        print(f"{C_AGENT}  ✅ Material guardado en: {ruta_salida}{C_RESET}")
    except Exception as e:
        return json.dumps({"error": f"Error guardando archivo: {e}"}, ensure_ascii=False)

    print(f"\n{C_LINE}{'═'*60}")
    print(f"✅ PIPELINE COMPLETADO — {tipo_pieza}: {tema}")
    print(f"   📄 Archivo: {ruta_salida}")
    print(f"   ⏱️  Duración: {duracion:.1f}s | 🤖 LLM: {metricas['llamadas_llm']} calls | 🔍 Web: {metricas['busquedas_web']} queries")
    print(f"   🟡 Estado: PENDIENTE DE REVISIÓN HUMANA")
    print(f"{'═'*60}{C_RESET}\n")

    return json.dumps({
        "estado": "completado",
        "tipo_pieza": tipo_pieza,
        "tema": tema,
        "archivo": ruta_salida,
        "metricas": metricas,
        "duracion_segundos": round(duracion, 1),
        "requiere_revision_humana": True
    }, ensure_ascii=False)


def ejecutar_arnes_marketing(ruta_briefing):
    """Ejecuta el arnés de marketing completo leyendo un archivo JSON de briefing.

    El archivo JSON debe contener un array 'piezas' con los briefings individuales.
    Genera todos los materiales y un reporte de ejecución final.
    No publica nada; todos los materiales quedan locales para revisión humana."""

    inicio_total = datetime.now()

    print(f"\n{C_BOLD}{'🎯 '*15}")
    print(f"  ARNÉS DE MARKETING AVRIL LAB — EJECUCIÓN COMPLETA")
    print(f"{'🎯 '*15}{C_RESET}\n")

    # Leer el archivo de briefing
    if not os.path.exists(ruta_briefing):
        return f"Error: No se encontró el archivo de briefing '{ruta_briefing}'."

    try:
        with open(ruta_briefing, "r", encoding="utf-8") as f:
            contenido = json.load(f)
    except (json.JSONDecodeError, Exception) as e:
        return f"Error leyendo briefing JSON '{ruta_briefing}': {e}"

    piezas = contenido.get("piezas", [contenido] if "tipo_pieza" in contenido else [])
    if not piezas:
        return "Error: El briefing no contiene piezas para generar. Formato esperado: {\"piezas\": [...]}"

    print(f"  📦 Piezas a generar: {len(piezas)}\n")

    resultados = []
    for i, pieza in enumerate(piezas, 1):
        print(f"\n{C_BOLD}{'─'*50}")
        print(f"  📌 Pieza {i}/{len(piezas)}: {pieza.get('tipo_pieza', '?')} — {pieza.get('tema', '?')}")
        print(f"{'─'*50}{C_RESET}")

        resultado = generar_contenido_marketing(pieza)
        try:
            resultados.append(json.loads(resultado))
        except (json.JSONDecodeError, TypeError):
            resultados.append({"error": str(resultado)})

    duracion_total = (datetime.now() - inicio_total).total_seconds()

    # Generar reporte de ejecución
    reporte = {
        "fecha_ejecucion": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "briefing_usado": ruta_briefing,
        "piezas_solicitadas": len(piezas),
        "piezas_completadas": sum(1 for r in resultados if r.get("estado") == "completado"),
        "piezas_fallidas": sum(1 for r in resultados if "error" in r),
        "duracion_total_segundos": round(duracion_total, 1),
        "tokens_totales_estimados": sum(r.get("metricas", {}).get("tokens_estimados", 0) for r in resultados if isinstance(r, dict)),
        "resultados": resultados,
        "requiere_revision_humana": True
    }

    # Guardar reporte
    os.makedirs(DIRECTORIO_OUTPUT_MARKETING, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    ruta_reporte = os.path.join(DIRECTORIO_OUTPUT_MARKETING, f"reporte_ejecucion_{timestamp}.json")

    try:
        with open(ruta_reporte, "w", encoding="utf-8") as f:
            json.dump(reporte, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"{C_ERROR}Error guardando reporte: {e}{C_RESET}")

    # Resumen final
    print(f"\n{C_LINE}{'═'*60}")
    print(f"📊 REPORTE FINAL DE EJECUCIÓN")
    print(f"{'═'*60}{C_RESET}")
    print(f"  📅 Fecha: {reporte['fecha_ejecucion']}")
    print(f"  📦 Piezas completadas: {reporte['piezas_completadas']}/{reporte['piezas_solicitadas']}")
    if reporte["piezas_fallidas"] > 0:
        print(f"  ❌ Piezas fallidas: {reporte['piezas_fallidas']}")
    print(f"  ⏱️  Duración total: {duracion_total:.1f} segundos")
    print(f"  🔢 Tokens totales estimados: {reporte['tokens_totales_estimados']}")
    print(f"  📁 Reporte guardado en: {ruta_reporte}")
    print(f"  🟡 Estado: TODOS LOS MATERIALES REQUIEREN REVISIÓN HUMANA")
    print(f"{'═'*60}")

    for r in resultados:
        if isinstance(r, dict) and r.get("archivo"):
            print(f"  📄 {r.get('tipo_pieza', '?')}: {r['archivo']}")

    print()
    return json.dumps(reporte, indent=2, ensure_ascii=False)


# --- MAPPING DE HERRAMIENTAS Y SCHEMA PARA FUNCTION CALLING ---

HERRAMIENTAS_DISPONIBLES = {
    "ejecutar_comando_terminal": ejecutar_comando_terminal,
    "web_search": web_search,
    "buscar_en_web": web_search,
    "web_fetch": web_fetch,
    "browser": browser,
    "abrir_url_en_navegador": abrir_url_en_navegador,
    "consultar_mcp_avril_knowledge": consultar_mcp_avril_knowledge,
    "consultar_base_datos_sqlite": consultar_base_datos_sqlite,
    "listar_archivos_carpeta": listar_archivos_carpeta,
    "buscar_archivos": buscar_archivos,
    "leer_archivo_local": leer_archivo_local,
    "modificar_archivo_local": modificar_archivo_local,
    "abrir_archivo_en_sistema": abrir_archivo_en_sistema,
    "generar_contenido_marketing": generar_contenido_marketing,
    "ejecutar_arnes_marketing": ejecutar_arnes_marketing
}

tools = [
    {
        "type": "function",
        "function": {
            "name": "ejecutar_comando_terminal",
            "description": "Ejecuta comandos de terminal o consola de comandos (Python, GCC, Git, etc.).",
            "parameters": {
                "type": "object",
                "properties": {
                    "comando": {"type": "string", "description": "Comando a ejecutar en la consola"}
                },
                "required": ["comando"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Busca en la web en tiempo real con soporte de filtros (país, idioma, frescura, cantidad).",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Texto de búsqueda en la web"},
                    "count": {"type": "integer", "description": "Número de resultados (por defecto 5)"},
                    "country": {"type": "string", "description": "Filtro de país (ej. 'MX', 'US')"},
                    "language": {"type": "string", "description": "Filtro de idioma (ej. 'es', 'en')"},
                    "freshness": {"type": "string", "description": "Filtro de frescura (ej. '30d', '24h', 'pw')"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "buscar_en_web",
            "description": "Alias de web_search: Busca información en la web en tiempo real.",
            "parameters": {
                "type": "object",
                "properties": {
                    "consulta": {"type": "string", "description": "Texto de búsqueda en la web"}
                },
                "required": ["consulta"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "web_fetch",
            "description": "Extrae el contenido de texto limpio y legible de una página web a partir de su URL.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL de la página web (http:// o https://)"},
                    "max_chars": {"type": "integer", "description": "Límite máximo de caracteres extraídos (por defecto 4000)"}
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser",
            "description": "Abre una página o enlace web directamente en el navegador del usuario.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL que se abrirá en el navegador"}
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "abrir_url_en_navegador",
            "description": "Alias de browser: Abre una URL web directamente en el navegador predeterminado.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL a abrir en el navegador"}
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "consultar_mcp_avril_knowledge",
            "description": "Consulta el servidor MCP avril-knowledge (autoridad en decisiones de arquitectura y estado de Avril Systems).",
            "parameters": {
                "type": "object",
                "properties": {
                    "accion": {
                        "type": "string",
                        "enum": ["get_current_state", "get_decision", "list_namespaces", "query_knowledge"],
                        "description": "Acción a consultar en el MCP"
                    },
                    "namespace": {
                        "type": "string",
                        "enum": ["canonical", "research", "current-state", "sources", "glossary"],
                        "description": "Namespace semántico a consultar"
                    },
                    "query": {"type": "string", "description": "Término o pregunta específica"}
                },
                "required": ["accion"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "consultar_base_datos_sqlite",
            "description": "Ejecuta consultas SELECT o modificaciones SQL en una base de datos local SQLite.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ruta_db": {"type": "string", "description": "Ruta del archivo de base de datos (.db)"},
                    "query_sql": {"type": "string", "description": "Consulta SQL a ejecutar"}
                },
                "required": ["ruta_db", "query_sql"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "listar_archivos_carpeta",
            "description": "Explora y lista archivos y carpetas en cualquier directorio del sistema.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ruta_dir": {"type": "string", "description": "Ruta de la carpeta a explorar"}
                },
                "required": ["ruta_dir"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "buscar_archivos",
            "description": "Busca recursivamente archivos en el sistema por nombre o extensión.",
            "parameters": {
                "type": "object",
                "properties": {
                    "nombre": {"type": "string", "description": "Patrón o nombre a buscar"},
                    "directorio": {"type": "string", "description": "Directorio base de búsqueda (opcional, por defecto '.')"}
                },
                "required": ["nombre"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "leer_archivo_local",
            "description": "Lee el contenido de un archivo de texto, código, o extrae el texto de documentos Word (.docx).",
            "parameters": {
                "type": "object",
                "properties": {
                    "ruta": {"type": "string", "description": "Ruta del archivo a leer"}
                },
                "required": ["ruta"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "modificar_archivo_local",
            "description": "Crea o modifica un archivo de cualquier tamaño (código largo, reportes detallados, etc.).",
            "parameters": {
                "type": "object",
                "properties": {
                    "ruta": {"type": "string", "description": "Ruta del archivo"},
                    "contenido": {"type": "string", "description": "Contenido completo a escribir"}
                },
                "required": ["ruta", "contenido"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "abrir_archivo_en_sistema",
            "description": "Abre un archivo directamente en la pantalla usando la aplicación nativa predeterminada en Windows (Word, Notepad, etc.).",
            "parameters": {
                "type": "object",
                "properties": {
                    "ruta": {"type": "string", "description": "Ruta del archivo a abrir en pantalla"}
                },
                "required": ["ruta"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "generar_contenido_marketing",
            "description": "Ejecuta el pipeline de marketing de Avril Lab: briefing → investigación web → generación de copy → fact-check → material .md listo para revisión humana. No publica nada automáticamente.",
            "parameters": {
                "type": "object",
                "properties": {
                    "briefing_json": {
                        "type": "string",
                        "description": "JSON string con campos: oferta, audiencia, cta, tipo_pieza (post/carrusel/guion), tema, contexto_extra (opcional)"
                    }
                },
                "required": ["briefing_json"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "ejecutar_arnes_marketing",
            "description": "Ejecuta el arnés de marketing completo leyendo un archivo JSON de briefing con múltiples piezas. Genera todos los materiales y un reporte de ejecución.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ruta_briefing": {
                        "type": "string",
                        "description": "Ruta al archivo JSON de briefing (ej. 'briefing_ejemplo.json')"
                    }
                },
                "required": ["ruta_briefing"]
            }
        }
    }
]



# --- EJECUCIÓN AUTÓNOMA DEL AGENTE ---

def ejecutar_agente(peticion: str) -> str:
    """Ejecuta el ciclo de razonamiento y herramientas del agente para una instrucción dada."""
    if not peticion:
        return "No se proporcionó ninguna instrucción."

    contexto_memoria = cargar_memoria_contexto()
    fecha_actual = datetime.now().strftime("%Y-%m-%d")

    system_prompt = f"""Eres un Agente Inteligente Multitarea experto en desarrollo de software, ciberseguridad y automatización en Windows.

MEMORIA DEL USUARIO:
{contexto_memoria}

══════════════════════════════════════════
REGLA TEMPORAL Y ANTI-ALUCINACIÓN (OBLIGATORIA)
══════════════════════════════════════════
La fecha y año actual es: {fecha_actual}. 
- Utiliza siempre el año actual ({datetime.now().year}) para cualquier búsqueda web sobre novedades, lanzamientos o "lo más reciente".
- NUNCA asumas un año en el pasado (como 2024) a menos que el usuario lo pida explícitamente en su consulta.
- Si la consulta es sobre versiones, documentación, noticias o hechos recientes, ejecuta buscar_en_web ANTES de responder. Nunca respondas de memoria sobre datos que pueden estar desactualizados.

══════════════════════════════════════════
HERRAMIENTAS DISPONIBLES (usa SOLO estas)
══════════════════════════════════════════

1. ejecutar_comando_terminal(comando)
   Ejecuta comandos de terminal (Python, Git, compiladores, Docker, LaTeX).
   NUNCA uses esto para tareas que cubren las herramientas 2-12.

2. web_search(query, count, country, language, freshness) / buscar_en_web(consulta)
   Busca información en internet en tiempo real con filtros avanzados.

3. web_fetch(url, max_chars)
   Extrae y lee el contenido limpio de una página web específica a partir de su URL.

4. browser(url) / abrir_url_en_navegador(url)
   Abre una página o enlace web en el navegador del usuario.

5. consultar_mcp_avril_knowledge(accion, namespace, query)
   Consulta la base de conocimiento y estado autoritativo de Avril Systems (MCP).

6. consultar_base_datos_sqlite(ruta_db, query_sql)
   Ejecuta consultas SQL en una base de datos SQLite local.

7. listar_archivos_carpeta(ruta_dir)
   Lista archivos y directorios en una ruta.

8. buscar_archivos(nombre, directorio)
   Busca archivos recursivamente por coincidencia de nombre.

9. leer_archivo_local(ruta)
   Lee archivos de texto, código o Word (.docx).

10. modificar_archivo_local(ruta, contenido)
    Crea o sobreescribe un archivo con el contenido dado.

11. abrir_archivo_en_sistema(ruta)
    Abre un archivo local en la aplicación nativa de Windows (Word, Notepad, etc.).

══════════════════════════════════════════
REGLAS DE ROUTING (OBLIGATORIAS)
══════════════════════════════════════════

- Buscar en internet        → SIEMPRE: web_search.           NUNCA: ejecutar_comando_terminal.
- Extraer texto de una web  → SIEMPRE: web_fetch.            NUNCA: ejecutar_comando_terminal con curl/requests.
- Abrir URL en navegador    → SIEMPRE: browser.              NUNCA: ejecutar_comando_terminal con start url.
- Consultar Avril Systems   → SIEMPRE: consultar_mcp_avril_knowledge.
- Leer un archivo local     → SIEMPRE: leer_archivo_local.   NUNCA: ejecutar_comando_terminal con cat/type.
- Listar directorio         → SIEMPRE: listar_archivos_carpeta. NUNCA: ejecutar_comando_terminal con dir/ls.
- Buscar archivos           → SIEMPRE: buscar_archivos.      NUNCA: ejecutar_comando_terminal con find/where.
- Abrir archivo del sistema → SIEMPRE: abrir_archivo_en_sistema. NUNCA: ejecutar_comando_terminal con start.
- Crear/editar archivo      → SIEMPRE: modificar_archivo_local. NUNCA: ejecutar_comando_terminal con echo/redirect.
- Consultas SQL             → SIEMPRE: consultar_base_datos_sqlite. NUNCA: ejecutar_comando_terminal con sqlite3.
- Compilar, git, pip, Docker, LaTeX, pytest → ejecutar_comando_terminal (uso legítimo).

══════════════════════════════════════════
LINEAMIENTOS OPERACIONALES Y GTM (AVRIL LAB)
══════════════════════════════════════════

1. USO DE BÚSQUEDA WEB Y LECTURA DE PÁGINAS (web_fetch vs. web_search):
   - La función 'web_fetch' DEBE emplearse para extraer y leer contenido de URLs específicas (http/https) para la verificación de hechos.
   - Si requieres consultar información externa, prioriza la extracción directa de fuentes verificables mediante 'web_fetch' o los módulos de búsqueda web integrados en runtime ('web_search').

2. DEFINICIÓN DEL ICP (Ideal Customer Profile) DE AVRIL LAB:
   - Audiencia objetivo: Builders, founders y perfiles técnicos curiosos ubicados en México y Latinoamérica (MX-LATAM).
   - Enfoque: Desarrolladores e ingenieros que construyen o prueban agentes de IA, integraciones MCP, o automatizaciones, y que necesitan entornos aislados/hosted de testing sin lidiar con la configuración de servidores ni el consumo de recursos de sus máquinas locales.

3. OFERTAS COMERCIALES ESTRUCTURADAS DE AVRIL LAB:
   - Day Pass: $6 USD por 48 horas de acceso a un seat alojado/hosted.
   - Trial: $15 USD por 7 días de acceso continuo.
   - Regla de venta/copy: Cada pieza de contenido o propuesta DEBE incluir una clara llamada a la acción (CTA).

══════════════════════════════════════════
MODOS ESPECIALIZADOS
══════════════════════════════════════════

AUDITOR DE SEGURIDAD (si piden auditar código):
  1. leer_archivo_local → leer el código fuente.
  2. Analizar vulnerabilidades (inyección SQL, credenciales, validación).
  3. modificar_archivo_local → generar reporte o parche.

ARQUITECTO DE PRUEBAS (si piden pruebas unitarias):
  1. leer_archivo_local → leer el código a probar.
  2. modificar_archivo_local → crear test_*.py con unittest.
  3. ejecutar_comando_terminal → python -m pytest test_*.py para verificar.

SINTETIZADOR DE MEMORIA (si piden actualizar memoria):
  1. leer_archivo_local("MEMORIA.md") → leer estado actual.
  2. modificar_archivo_local("MEMORIA.md", contenido) → actualizar con resúmenes concisos.

ESTRATEGA DE CONTENIDO Y GTM AVRIL LAB (si piden redactar propuestas, copies o mensajes para prospectos):
  1. Alinear con el ICP de Builders/founders técnicos en MX-LATAM.
  2. Aplicar las ofertas oficiales: Day Pass ($6 USD / 48h) o Trial ($15 USD / 7d).
  3. Incluir obligatoriamente un Call To Action (CTA) claro y persuasivo.
  4. Si se citan hechos, empresas o noticias, verificarlos primero mediante web_fetch o web_search.
  5. Para generar materiales de marketing completos, usar generar_contenido_marketing o ejecutar_arnes_marketing.

12. generar_contenido_marketing(briefing_json)
    Pipeline completo: briefing → investigación → copy → fact-check → material .md.
    Úsalo cuando pidan crear contenido de marketing para Avril Lab.

13. ejecutar_arnes_marketing(ruta_briefing)
    Ejecuta el arnés completo desde un archivo JSON con múltiples piezas.
    Úsalo cuando den una ruta a un archivo de briefing.
"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": peticion}
    ]

    iteraciones = 0
    while iteraciones < MAX_ITERACIONES_HERRAMIENTAS:
        iteraciones += 1
        print(f"\n{C_WARN}🤖 Procesando petición con {MODELO}... (iteración {iteraciones}/{MAX_ITERACIONES_HERRAMIENTAS}){C_RESET}")
        try:
            response = client.chat.completions.create(
                model=MODELO,
                messages=messages,
                tools=tools,
                tool_choice="auto",
                temperature=0.1
            )
            
            response_message = response.choices[0].message
            
            if response_message.tool_calls:
                messages.append(response_message)
                
                for tool_call in response_message.tool_calls:
                    func_name = tool_call.function.name
                    try:
                        func_args = json.loads(tool_call.function.arguments)
                    except json.JSONDecodeError as je:
                        resultado = f"Error: argumentos JSON inválidos del modelo: {je}"
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "name": func_name,
                            "content": resultado
                        })
                        print(f"\n{C_ERROR}💡 {resultado}{C_RESET}")
                        continue
                    
                    if func_name not in HERRAMIENTAS_DISPONIBLES:
                        resultado = f"Error: herramienta '{func_name}' no existe. Usa solo: {', '.join(HERRAMIENTAS_DISPONIBLES.keys())}"
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "name": func_name,
                            "content": resultado
                        })
                        print(f"\n{C_ERROR}💡 {resultado}{C_RESET}")
                        continue
                    
                    # Validar parámetros antes de ejecutar
                    func = HERRAMIENTAS_DISPONIBLES[func_name]
                    sig = inspect.signature(func)
                    try:
                        sig.bind(**func_args)
                    except TypeError as bind_err:
                        resultado = f"Error de parámetros en '{func_name}': {bind_err}. Parámetros esperados: {list(sig.parameters.keys())}"
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "name": func_name,
                            "content": resultado
                        })
                        print(f"\n{C_ERROR}💡 {resultado}{C_RESET}")
                        continue
                    
                    print(f"{C_WARN}📌 Agente ejecuta: {func_name}({', '.join(f'{k}={v!r}' for k, v in func_args.items())}){C_RESET}")
                    resultado = func(**func_args)
                    
                    if "Error" in resultado or "Denegado" in resultado:
                        print(f"\n{C_ERROR}💡 Resultado: {resultado}{C_RESET}")
                    else:
                        print(f"\n{C_AGENT}💡 Resultado: {resultado[:300]}...{C_RESET}" if len(resultado) > 300 else f"\n{C_AGENT}💡 Resultado: {resultado}{C_RESET}")
                    
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": func_name,
                        "content": str(resultado)
                    })
            else:
                respuesta_texto = extraer_texto_mensaje(response_message)
                respuesta_texto = limpiar_wrappers_innecesarios(respuesta_texto)
                print(f"\n{C_AGENT}🤖 RESPUESTA DEL AGENTE:\n{respuesta_texto}{C_RESET}\n")
                enviar_notificacion_sistema(
                    "✅ Tarea Finalizada", 
                    "El agente ha terminado lo que le pediste. Ya puedes revisarlo.", 
                    es_error=False
                )
                return respuesta_texto
                
        except Exception as e:
            msg_error = str(e)
            print(f"\n{C_ERROR}❌ Error en el Agente: {msg_error}{C_RESET}\n")
            enviar_notificacion_sistema(
                "🔴 Error en el Agente", 
                f"Hubo un fallo: {msg_error[:50]}...", 
                es_error=True
            )
            return f"Error en el Agente: {msg_error}"
    
    msg_limite = f"⚠️ Se alcanzó el límite de {MAX_ITERACIONES_HERRAMIENTAS} iteraciones de herramientas. Deteniendo."
    print(f"\n{C_WARN}{msg_limite}{C_RESET}")
    return msg_limite

if __name__ == "__main__":
    import sys
    if "--marketing" in sys.argv:
        # Modo arnés de marketing: python agente.py --marketing [ruta_briefing.json]
        idx = sys.argv.index("--marketing")
        if idx + 1 < len(sys.argv):
            ruta = sys.argv[idx + 1]
        else:
            ruta = "briefing_ejemplo.json"
        print(f"{C_LINE}{'═'*60}")
        print(f"  ARNÉS DE MARKETING AVRIL LAB (C2)")
        print(f"  Briefing: {ruta}")
        print(f"{'═'*60}{C_RESET}")
        resultado = ejecutar_arnes_marketing(ruta)
        print(f"\n{C_AGENT}Resultado final:{C_RESET}")
        print(resultado)
    elif "--chat" in sys.argv:
        print(f"{C_LINE}Agente listo. Escribe 'salir' para terminar.{C_RESET}")
        while True:
            try:
                entrada = input(f"{C_USER}Tú: {C_RESET}").strip()
            except (KeyboardInterrupt, EOFError):
                break
            if entrada.lower() in ("salir", "exit", "quit"):
                break
            if entrada:
                ejecutar_agente(entrada)
    else:
        uvicorn.run(app, host="127.0.0.1", port=8000)
