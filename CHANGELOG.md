# Registro de cambios

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/).
Este proyecto usa [versionado semántico](https://semver.org/lang/es/).

## [Sin publicar]

El cliente del padrón corrió por primera vez contra ARCA, en homologación y con
un certificado emitido por WSASS. Funcionó de punta a punta después de corregir
tres cosas que los manuales no muestran.

### Corregido

- **El ticket del WSAA ahora se lee.** Llega como texto escapado dentro de
  `loginCmsReturn`, no como elementos, así que el cliente fallaba *después* de
  que ARCA lo emitía. Un reintento habría quedado bloqueado doce horas con
  `coe.alreadyAuthenticated`.
- **Si el ticket no se puede guardar en disco, no se pierde.** Un error al
  escribir la caché (permisos, disco lleno) avisa con un `RuntimeWarning` y
  devuelve el ticket igual; antes la excepción lo tiraba a la basura recién
  emitido, con el mismo bloqueo de doce horas. Lo detectó la revisión de código.
- **La caché del ticket ahora sabe de qué certificado es.** WSAA ata cada
  ticket al certificado que firmó el pedido; dos certificados compartiendo el
  archivo se prestaban el ticket y el segundo era rechazado. El archivo guarda
  un ticket por ambiente, servicio y huella SHA-256 del certificado, sin que
  uno pise al otro. Un archivo de la versión anterior, que no anotaba el
  certificado, se sigue leyendo: descartarlo habría pedido otro ticket y
  recibido `coe.alreadyAuthenticated` hasta que venciera.
- **El temporal de la caché ya no tiene nombre predecible.** Se crea con
  `mkstemp` (exclusivo, `600`, sin seguir symlinks), se sincroniza a disco
  antes de reemplazar al anterior, y el directorio también. Antes, un symlink
  plantado en `.ticket.json.tmp` desviaba la credencial a donde apuntara.
- **Lo guardado se valida antes de usarse.** Un vencimiento sin zona horaria o
  un `token` que no es texto se tratan como ausentes, en vez de fallar en
  medio de una consulta.
- **El fault "No existe persona con ese Id" se reconoce aunque cambie la
  puntuación, el espaciado o las mayúsculas.** El texto exacto se observó una
  sola vez; una variante mínima habría convertido "CUIT desconocida" en error.
- **El mensaje de `ConstanciaUnavailable` es una sola línea acotada**, sin
  agujero cuando ARCA no manda `idPersona`. Los motivos siguen enteros en
  `.reasons`.
- **Una constancia bloqueada ya no se confunde con "no es monotributista".** Una
  CUIT cancelada, o bloqueada por falta de datos biométricos, lanza
  `ConstanciaUnavailable` con los motivos textuales de ARCA en vez de devolver
  `None`.
- **Un CUIT inexistente devuelve `None`.** El servicio lo dice con un SOAP fault,
  no con el `errorConstancia` del manual, y el cliente lo trataba como falla.

### Agregado

- **El ticket puede guardarse en disco** (`build_registry(ticket_cache=...)`),
  con permisos `600` y escritura atómica, para que un proceso nuevo no quede
  afuera mientras el anterior siga vigente.
- `build_registry` acepta un reloj, como ya lo hacía `ArcaRegistry`.
- Respuestas reales de homologación grabadas como fixtures, y un test que arma
  el cliente completo contra ellas. Reprodujo offline la falla del primer
  intento antes de corregirla.

### Verificado contra ARCA

En homologación: el esquema del TRA, la firma SHA256, el DN de `destination`, las
tolerancias de tiempo, `getPersona_v2` autenticado y el parseo de respuestas
reales. Queda sin verificar: producción y la delegación de un tercero.

## [0.3.0] - 2026-09-24

Las facturas escaneadas ahora se leen, las lecturas van en paralelo, la web
puede protegerse con una clave, y el padrón real de ARCA tiene un cliente
verificado contra los manuales oficiales.

### Agregado

- **OCR para facturas escaneadas** (`--extra ocr`, más el binario `tesseract`).
  Un PDF sin capa de texto se lee reconociendo los píxeles. Sin el extra, el
  archivo se rechaza en vez de saltearse: una factura omitida bajaría el
  acumulado sin que nadie se entere.
- **Aviso cuando se usó OCR.** El reconocimiento adivina, así que todo caso que
  lo usó va a un contador aunque los números den tranquilos, y el informe
  nombra los archivos a cotejar contra el original.
- **Clave de acceso para la web** (`COPILOTO_TOKEN`). Sin definirla, la
  interfaz queda abierta, que es lo correcto para una laptop y por eso el
  servidor escucha en localhost. Definida, todo pide sesión salvo el login y la
  hoja de estilos. La cookie lleva un HMAC, nunca la clave.
- **Aviso al publicar sin clave.** Servir fuera de localhost sin
  `COPILOTO_TOKEN` imprime una advertencia nombrando lo que queda expuesto.
- **Cliente del padrón real de ARCA** (`--extra arca`), en `copiloto.arca`:
  ticket del WSAA, firma CMS, sobres SOAP, parseo de la constancia y un
  `ArcaRegistry` que implementa el mismo Protocol que el padrón simulado.
- **`docs/arca-padron.md`**, con el camino de integración, el modelo de
  delegación y una sección que separa qué se verificó contra el servicio en
  vivo de qué no puede verificarse sin certificado.

### Cambiado

- **Las facturas se leen en paralelo.** El grafo reparte una tarea por
  comprobante con `Send` en un solo superstep. Doce facturas a 0,8 s cada
  lectura pasaron de 9,6 s a 0,82 s. Si el proceso muere a mitad de camino,
  reanudar relee solo la factura interrumpida: LangGraph conserva lo que las
  otras tareas ya escribieron, que con un proveedor pago es la diferencia entre
  un cargo y doce.
- **El resultado se ordena cronológicamente** al juntar las tareas, para que dos
  corridas sobre la misma carpeta coincidan sin depender de cómo el framework
  programe el trabajo.
- `sources.py` expone `load_invoice_sources`, que informa de dónde salió cada
  texto. `load_invoice_texts` sigue existiendo para quien no lo necesita.
- La CI instala primero sin extras para probar que un clone limpio funciona, y
  después con todos para chequear tipos y correr el OCR real.

### Corregido

- La firma del TRA usa **SHA256**, no el SHA1 que pide la especificación 1.2.2.
  `cryptography` rechaza SHA1 de plano y `pyafipws`, que opera contra el
  servicio real, usa SHA256. Seguir la documentación al pie de la letra produce
  código que no arranca.
- Los tests de los extras ya no rompen la recolección en una instalación limpia.

### Verificado contra ARCA

Sin certificado se pudo comprobar: los endpoints del padrón (`dummy()` responde
`OK` en homologación y producción), el contrato de los dos WSDL, el sobre SOAP
y sus namespaces, el parseo de respuestas y faults, y que ARCA lee el mensaje
firmado.

No se pudo comprobar, y está dicho así: el esquema del TRA, la aceptación de
SHA256, el DN de `destination`, las tolerancias de tiempo, y `getPersona_v2`,
que nunca se ejecutó. ARCA valida el certificado antes que todo lo demás — se
confirmó mandando un TRA deliberadamente roto y recibiendo el mismo error que
con uno válido.

## [0.2.0] - 2026-09-24

El copiloto dejó de ser una demo de terminal: se usa desde el navegador y le
deja el caso a un contador que no está en ese teclado.

### Agregado

- **Margen de facturación.** Cuánto podés facturar antes del tope de tu
  categoría y del régimen, y cuántos meses te quedan al ritmo reciente. La
  cuenta de meses es una heurística propia y el informe lo declara.
- **Parámetros físicos declarados** (`--surface-m2`, `--energy-kwh`,
  `--annual-rent`). Se evalúan contra la misma tabla de ARCA: la categoría es la
  del parámetro más alto, y superar el máximo de K es causal de exclusión. Lo
  no declarado queda en "No evaluado", nunca se asume cero.
- **Checkpoints en SQLite** (`--state-db`), para que un caso pausado sobreviva
  al proceso.
- **Servicio compartido** (`copiloto.service.Copilot`) con arrancar, consultar,
  reanudar y listar, usado por igual desde la CLI y la web.
- **Comandos nuevos**: `run --no-wait` (deja el caso y sale con código 3),
  `cases`, `review` y `serve`.
- **Interfaz web** en FastAPI, renderizada en el servidor y en español:
  formulario con subida de facturas, los catorce ejemplos para probar sin
  modelo, página de alerta con el veredicto del contador, informe y lista de
  casos. Cada caso es una URL que se abre más tarde desde otra máquina.

### Seguridad

- El markdown se renderiza con HTML deshabilitado, así que las notas del
  contador y el texto extraído por el modelo se escapan en vez de inyectarse.

## [0.1.0] - 2026-09-23

Primera versión: el grafo completo, de las facturas al informe.

### Agregado

- Tabla de ARCA versionada en `config/`, con fecha de vigencia y fuente citada.
- Validación de CUIT por módulo 11, de montos contra el precio unitario máximo,
  y de fechas contra la ventana móvil de doce meses.
- Análisis: acumulado, categoría que corresponde, proyección y nivel de riesgo.
- Informe en español rioplatense, con sus límites escritos adentro.
- Grafo de LangGraph con pausa para revisión humana vía `interrupt`, y diagrama
  Mermaid exportado del grafo compilado, no dibujado a mano.
- Tres extractores detrás de un Protocol: `fake` (determinista, sin red), `cli`
  (usa la herramienta de IA que ya tengas) y `api` (con clave de proveedor).
- Padrón simulado con CUITs sintéticos, incluido el caso válido-pero-desconocido.
- Catorce casos de evaluación con respuestas calculadas a mano, y un runner que
  puntúa decisión y extracción por separado.
- CLI con revisión interactiva del contador.
- CI que prueba que un clone limpio corre todo sin API key, sin herramienta de
  IA y sin red.

[Sin publicar]: https://github.com/leonardoprimero/copiloto-monotributo/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/leonardoprimero/copiloto-monotributo/releases/tag/v0.3.0
[0.2.0]: https://github.com/leonardoprimero/copiloto-monotributo/releases/tag/v0.2.0
[0.1.0]: https://github.com/leonardoprimero/copiloto-monotributo/releases/tag/v0.1.0
