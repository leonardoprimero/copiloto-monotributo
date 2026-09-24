# Consultar el padrón real de ARCA

El copiloto trae un padrón simulado: una tabla en memoria con CUITs sintéticos
que responde qué categoría tiene declarada cada uno. Alcanza para la demo, los
evals y los tests, y no toca la red.

Este documento describe la otra implementación, la que consulta el padrón real.
Está escrita contra los manuales oficiales y **se ejecutó de punta a punta en
homologación** con un certificado emitido por ARCA: ticket del WSAA, consulta
autenticada y respuestas reales. Producción no se probó. El repositorio no
trae ni pide ningún certificado. La sección [Qué se verificó y qué
no](#qué-se-verificó-y-qué-no) dice exactamente cuál es cuál.

## Lo primero: puede que no la necesites

El padrón devuelve la categoría en la que el contribuyente está inscripto. Es
decir: una letra que el contribuyente ya sabe, y que la CLI y la web ya piden
con `--category`. El copiloto no la usa para nada más.

Sirve cuando quien corre el copiloto no es el contribuyente —un estudio
contable con varios clientes, por ejemplo— y escribir la categoría a mano de a
uno es una fuente de errores. Para una persona mirando sus propias facturas, no
agrega nada.

## Cómo funciona la autorización

Esta es la parte que importa, porque es la que sostiene una promesa del
proyecto: **el copiloto nunca pide la clave fiscal de nadie.**

El certificado es tuyo, no del contribuyente. El contribuyente te autoriza
desde su propio Administrador de Relaciones de Clave Fiscal, y puede sacarte
esa autorización cuando quiera, sin avisarte y sin pedirte nada.

1. Tramitás tu certificado digital X.509 ante la Autoridad Certificante de
   ARCA. Para producción se usa la aplicación "Administrador de Certificados
   Digitales"; para testing, WSASS.
2. Asociás ese certificado al servicio `ws_sr_constancia_inscripcion` desde el
   Administrador de Relaciones de Clave Fiscal.
3. **El contribuyente** entra a *su* Administrador de Relaciones y delega ese
   servicio a tu CUIT.
4. El ticket que devuelve el WSAA trae una sección `relations`. El campo
   `cuitRepresentada` de cada consulta tiene que ser uno de esos CUITs. Ahí es
   donde la delegación se vuelve efectiva.

Si el paso 3 no ocurrió, el WSAA responde `coe.notAuthorized` y no hay consulta
posible. Es así por diseño, y está bien que sea así.

### Para probar en homologación

El certificado de testing se saca desde WSASS, con tu clave fiscal, y todo se
hace desde ahí: crear el certificado y autorizarlo al servicio. Tres cosas que
no están escritas en ningún lado y cuestan un intento cada una:

- **La clave privada se genera en tu máquina.** A WSASS solo le pegás el CSR:
  `openssl req -new -key clave.key -subj "/C=AR/O=.../CN=.../serialNumber=CUIT
  20XXXXXXXXX"`. El `serialNumber` tiene que ser el CUIT de la sesión.
- **El nombre simbólico del DN admite solo letras y números.** Con un guion,
  WSASS rechaza el formulario.
- **WSASS reemplaza el CN del CSR por ese nombre simbólico.** El DN emitido es
  `SERIALNUMBER=CUIT ..., CN=<alias>`, así que el CN que pusiste no importa.

Para probar sin un tercero, la CUIT representada puede ser la tuya: WSASS
autoriza el servicio sobre tu propia CUIT en el mismo formulario.

## El flujo técnico

### WSAA: conseguir el ticket

Fuente: *Especificación Técnica del WebService de Autenticación y Autorización*,
versión 1.2.2.

1. Armar el `LoginTicketRequest.xml` con `uniqueId`, `generationTime`,
   `expirationTime` y el nombre del servicio.
2. Firmarlo como un mensaje CMS `SignedData` con SHA1+RSA, incluyendo el
   certificado X.509.
3. Codificarlo en Base64.
4. Invocar `loginCms` y leer `token` y `sign` del `LoginTicketResponse.xml`.

El paso 4 tiene una trampa que el manual no muestra. Su ejemplo es el
`LoginTicketResponse.xml` pelado; lo que llega por la red es un sobre SOAP cuyo
`loginCmsReturn` trae ese documento **como texto escapado**. Leerlo como
elementos no encuentra ningún `<token>`, y para ese momento ARCA ya emitió el
ticket. El primer intento real de este cliente falló exactamente así, y un
reintento habría quedado bloqueado doce horas. `parse_login_response` desarma el
sobre antes de leer el ticket.

| Ambiente | Endpoint del WSAA |
| --- | --- |
| Producción | `https://wsaa.afip.gov.ar/ws/services/LoginCms` |
| Homologación | `https://wsaahomo.afip.gov.ar/ws/services/LoginCms` |

Tres reglas del manual que el código respeta y que conviene tener presentes:

- **El ticket dura 12 horas y hay que reusarlo.** Pedir otro teniendo uno
  válido devuelve `coe.alreadyAuthenticated`, que es un error. Por eso
  `ArcaRegistry` cachea el ticket, y con `ticket_cache=` lo guarda en disco
  para que sobreviva al proceso: si no, el siguiente proceso queda afuera
  hasta que venza. No es una optimización.
- `generationTime` admite hasta 24 horas de antigüedad y `expirationTime` hasta
  24 horas hacia adelante. Fuera de eso la solicitud se rechaza, y la causa
  habitual es un reloj desincronizado.
- Ante errores que no sean `wsaa.*` ni `wsn.unavailable`, el manual pide no
  reintentar hasta haber resuelto el problema. No los trates como transitorios.

### Padrón: consultar la constancia

Fuente: *Consulta a Padrón Constancia de Inscripción `ws_sr_constancia_inscripcion`,
Manual para el desarrollador*, versión 3.4 (08/05/23).

| Ambiente | Endpoint |
| --- | --- |
| Producción | `https://aws.afip.gov.ar/sr-padron/webservices/personaServiceA5` |
| Homologación | `https://awshomo.afip.gov.ar/sr-padron/webservices/personaServiceA5` |

El id de servicio a pedirle al WSAA es `ws_sr_constancia_inscripcion` (antes se
llamaba `ws_sr_padron_a5`). El método vigente es `getPersona_v2(token, sign,
cuitRepresentada, idPersona)`; `getPersonaList_v2` acepta hasta 250 CUITs.
`dummy()` verifica disponibilidad y es el único método sin autenticación.

La respuesta trae `datosGenerales` y después `datosMonotributo` o
`datosRegimenGeneral`. El copiloto lee **solo** la categoría de monotributo. El
resto es el perfil fiscal de una persona y no es asunto suyo: no se guarda, no
se loguea y no se pasa a nadie.

Cuando no hay constancia, el servicio real no se comporta como el manual:

| Situación | Qué dice el manual | Qué responde el servicio | Qué devuelve `lookup` |
| --- | --- | --- | --- |
| El CUIT no existe | `errorConstancia` con `No existe persona con ese Id` | Un SOAP fault con ese mismo texto | `None` |
| El CUIT existe pero no se certifica (cancelado, bloqueado por datos biométricos) | Nada | `errorConstancia` con los motivos | `ConstanciaUnavailable`, con los motivos de ARCA textuales |
| Régimen general | `datosRegimenGeneral` | Igual | `None` |

El segundo caso es el que importa. Tratarlo como "no es monotributista" ocultaría
justo la situación que alguien necesita escuchar, así que es un error: una
subclase de `PadronError` con los motivos en `reasons`.

#### La categoría viene dos veces

```xml
<categoriaMonotributo>
  <descripcionCategoria>B LOCACIONES DE SERVICIO</descripcionCategoria>
  <idCategoria>36</idCategoria>
</categoriaMonotributo>
```

`idCategoria` es un código interno y el manual no publica su tabla. Así que la
letra se lee de `descripcionCategoria`, donde es la primera palabra. Inventar
un mapeo para `idCategoria` sería adivinar, y adivinar la categoría de alguien
es exactamente lo que este proyecto no hace. Si la descripción no empieza con
una letra de la A a la K, `parse_persona` falla en vez de devolver cualquier
cosa.

## El hash: la documentación dice SHA1 y eso no compila

La especificación 1.2.2 pide firmar el TRA con **SHA1+RSA**. Si seguís esa
línea al pie de la letra, no funciona:

```
TypeError: hash_algorithm must be one of hashes.SHA224, SHA256, SHA384, or SHA512
```

`cryptography` retiró SHA1 para firmas. Y `pyafipws` —la referencia en Python
que sí opera contra AFIP en producción— firma con **SHA256**:

```python
.add_signer(cert, private_key, hashes.SHA256())
```

Así que el texto del manual quedó viejo y acá se firma con SHA256. Está fijado
en un test, porque es el único lugar donde seguir la documentación literalmente
produce código que no corre.

## Qué hay implementado

Instalación: `uv sync --extra arca`.

| Módulo | Qué hace |
| --- | --- |
| `arca/wsaa.py` | Arma el TRA, parsea el TA, controla el vencimiento |
| `arca/signing.py` | Firma el TRA como CMS SignedData en base64 |
| `arca/soap.py` | Arma los sobres, los envía, traduce los faults |
| `arca/padron.py` | Parsea `personaReturn` a `TaxpayerProfile` |
| `arca/registry.py` | `ArcaRegistry`, implementa `TaxpayerRegistry`, cachea el ticket |
| `arca/ticket_cache.py` | Guarda el ticket en disco, con permisos de dueño y escritura atómica |
| `arca/client.py` | `build_registry(...)` y `service_status(...)` |

Con certificado, son dos llamadas:

```python
from pathlib import Path
from copiloto.arca.client import build_registry, service_status
from copiloto.arca.wsaa import HOMOLOGACION

print(service_status(HOMOLOGACION))   # {'appserver': 'OK', ...}

registro = build_registry(
    cert_path=Path("certificado.pem"),
    key_path=Path("clave.key"),
    represented_cuit="20-11111111-2",
    environment=HOMOLOGACION,
    ticket_cache=Path("ticket.json"),
)
perfil = registro.lookup("27-01594221-0")
```

`ticket_cache` es opcional, pero sin él el ticket muere con el proceso. El
archivo guarda una credencial: se crea con permisos `600` a través de un
temporal de nombre impredecible que reemplaza al anterior de un solo paso,
guarda un ticket por ambiente, servicio y certificado (WSAA ata el ticket a
los tres, y dos certificados pueden compartir el archivo sin pisarse), y si no
se puede leer o no corresponde se ignora. Un archivo guardado por una versión
anterior no tiene la huella del certificado y se sigue usando igual, porque
descartarlo pediría otro ticket y WSAA respondería `coe.alreadyAuthenticated`
hasta que venciera el anterior.

El transporte HTTP por defecto tiene un timeout y **ningún reintento**, a
propósito: el manual pide no reintentar ante la mayoría de los errores hasta
haber resuelto la causa. Se reemplaza con el parámetro `post`.

## Qué se verificó y qué no

Esta es la parte que importa si vas a confiarle algo.

### Verificado contra el servicio en vivo

| Qué | Cómo |
| --- | --- |
| Los endpoints del padrón | `dummy()` a homologación y a producción devolvió `appserver/authserver/dbserver: OK` |
| El sobre SOAP y su namespace | El servicio lo procesó y respondió con la forma documentada |
| El parseo de la respuesta y de los faults | Un método inexistente devolvió `No such operation 'nada'` |
| El contrato del WSDL | Bajado de `personaServiceA5?WSDL`: las cinco operaciones y los cuatro parámetros de `getPersona_v2` (`cuitRepresentada` e `idPersona` son `xs:long`, por eso los CUIT viajan sin guiones) |
| El contrato del WSAA | `loginCms(in0: string) → loginCmsReturn: string`, y el namespace del elemento es `http://wsaa.view.sua.dvadac.desein.afip.gov`, **distinto** del target namespace del servicio |
| La estructura del CMS | `openssl smime -verify` lo valida y devuelve el TRA intacto; `openssl asn1parse` confirma `pkcs7-signedData` |
| Que ARCA lee el CMS | Firmando con un certificado autofirmado, el WSAA de homologación responde `Certificado no emitido por AC de confianza`: llegó a leer el certificado adentro del mensaje |
| El TRA completo | Con un certificado emitido por WSASS, el WSAA de homologación emitió un ticket. Eso valida de una vez el esquema del TRA, la firma **SHA256**, el DN de `destination` de homologación y las tolerancias de tiempo |
| La respuesta real del WSAA | El ticket llega escapado dentro de `loginCmsReturn`, no como elementos. Grabada en `tests/arca/recorded.py` |
| `getPersona_v2` autenticado | Aceptado con `cuitRepresentada` igual a la CUIT del certificado. Un monotributista de la base de prueba volvió con categoría B, leída de una respuesta real |
| Un CUIT inexistente | SOAP fault `No existe persona con ese Id`, no un `errorConstancia` |
| Una constancia bloqueada | `errorConstancia` con tres motivos: CUIT cancelada, domicilio fiscal electrónico pendiente, y datos biométricos sin registrar |
| El ticket en disco | Tres consultas desde un proceso nuevo usaron el ticket guardado y ninguna volvió a llamar al WSAA |

Las respuestas grabadas son fixtures de `tests/arca/test_client.py`, que arma
el cliente completo y le responde con ellas. Ese test reprodujo offline la falla
del primer intento real antes de que se corrigiera.

### Cómo se llegó hasta acá

Sin certificado, ARCA valida el certificado **antes** que el resto. Se comprobó
mandando cuatro variantes con un certificado autofirmado —TRA válido, XML roto,
`destination` del ambiente equivocado y `expirationTime` vencido— y las cuatro
devolvieron el mismo error de certificado. Por eso nada del flujo autenticado
podía probarse sin tramitar uno en WSASS.

### Todavía sin verificar

- **Producción.** Otro certificado, otra autoridad certificante y otro DN de
  `destination`. Que homologación funcione lo hace probable, no seguro.
- **Una delegación de un tercero.** En homologación la CUIT representada fue la
  propia. Que otro contribuyente delegue desde su Administrador de Relaciones, y
  que eso aparezca en la sección `relations` del ticket, no se ejecutó.
- **`coe.alreadyAuthenticated`.** Está documentado y el caché existe para
  evitarlo, pero no se provocó a propósito para ver el mensaje exacto.
- **`getPersonaList_v2`**, que el cliente no usa.

Para correr el único test que toca la red:

```sh
COPILOTO_ARCA_LIVE=1 uv run pytest tests/arca/test_soap.py
```

Está apagado por defecto: una suite de tests no puede depender de que un
servicio del Estado esté levantado.

## Antes de usarlo en producción

- El padrón tiene **límites diarios de consultas** por CUIT representada.
  Cachear resultados, no solo el ticket.
- Los certificados vencen. `cms.cert.expired` es un error del WSAA, y conviene
  enterarse antes de que pase.
- Usá primero homologación. Los endpoints y los DN de destino son distintos en
  cada ambiente, y confundirlos da errores que parecen de permisos.
- Se probó en homologación, no en producción. Hacé tu propia prueba en
  homologación con tu certificado antes de confiarle un dato real.
