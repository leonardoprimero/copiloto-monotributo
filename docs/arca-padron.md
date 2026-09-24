# Consultar el padrón real de ARCA

El copiloto trae un padrón simulado: una tabla en memoria con CUITs sintéticos
que responde qué categoría tiene declarada cada uno. Alcanza para la demo, los
evals y los tests, y no toca la red.

Este documento describe la otra implementación, la que consulta el padrón real.
Está escrita contra los manuales oficiales y probada contra los ejemplos que
esos manuales publican. Parte se verificó además contra el servicio en vivo; el
resto **no puede verificarse sin un certificado**, y este repositorio no tiene
ni pide ninguno. La sección [Qué se verificó y qué
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

| Ambiente | Endpoint del WSAA |
| --- | --- |
| Producción | `https://wsaa.afip.gov.ar/ws/services/LoginCms` |
| Homologación | `https://wsaahomo.afip.gov.ar/ws/services/LoginCms` |

Tres reglas del manual que el código respeta y que conviene tener presentes:

- **El ticket dura 12 horas y hay que reusarlo.** Pedir otro teniendo uno
  válido devuelve `coe.alreadyAuthenticated`, que es un error. Por eso
  `ArcaRegistry` cachea el ticket; no es una optimización.
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

La respuesta trae `datosGenerales` y después `datosMonotributo`,
`datosRegimenGeneral`, o un `errorConstancia` si el CUIT no existe. El copiloto
lee **solo** la categoría de monotributo. El resto es el perfil fiscal de una
persona y no es asunto suyo: no se guarda, no se loguea y no se pasa a nadie.

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
)
perfil = registro.lookup("27-01594221-0")
```

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

### NO verificado, y por qué no se puede

ARCA valida el certificado **antes** que el resto. Se comprobó mandando cuatro
variantes con el mismo certificado autofirmado —TRA válido, XML roto,
`destination` del ambiente equivocado y `expirationTime` vencido— y las cuatro
devolvieron el mismo error de certificado.

Eso significa que lo siguiente **no quedó probado**, y no puede probarse sin un
certificado emitido por ARCA:

- que el XML del TRA pase su validación de esquema,
- que acepten la firma SHA256 (aunque `pyafipws` la usa en producción),
- que el DN de `destination` sea el correcto para cada ambiente,
- que las tolerancias de `generationTime` y `expirationTime` estén bien,
- y todo el flujo del padrón autenticado: `getPersona_v2` nunca se ejecutó.

El parseo de `personaReturn` está probado contra los ejemplos de respuesta del
manual, no contra respuestas reales.

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
- Nada de esto se probó contra ARCA. Probalo vos en homologación antes de
  confiarle un dato real.
