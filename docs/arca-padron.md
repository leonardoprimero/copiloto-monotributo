# Consultar el padrón real de ARCA

El copiloto trae un padrón simulado: una tabla en memoria con CUITs sintéticos
que responde qué categoría tiene declarada cada uno. Alcanza para la demo, los
evals y los tests, y no toca la red.

Este documento describe la otra implementación, la que consulta el padrón real.
Está escrita y probada contra los ejemplos de los manuales oficiales, pero
**nunca se ejecutó contra ARCA**: hace falta un certificado, y este repositorio
no tiene ni pide ninguno.

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

## Qué hay implementado y qué falta

Instalación: `uv sync --extra arca`.

| Módulo | Qué hace | Estado |
| --- | --- | --- |
| `arca/wsaa.py` | Arma el TRA, parsea el TA, controla el vencimiento | Probado contra los ejemplos del manual |
| `arca/padron.py` | Parsea `personaReturn` a `TaxpayerProfile` | Probado contra los ejemplos del manual |
| `arca/registry.py` | `ArcaRegistry`, implementa `TaxpayerRegistry`, cachea el ticket | Probado con dobles |
| Firma CMS | Firmar el TRA con el certificado | **No implementado** |
| Transporte SOAP | Hacer las llamadas HTTP | **No implementado** |

Los dos últimos son argumentos inyectados (`sign_cms`, `send`, `call_padron`),
no código faltante escondido: son la costura donde un despliegue pone su propio
transporte, sus timeouts y sus reintentos. Esas decisiones dependen de la
infraestructura de cada uno y no pertenecen a esta librería.

Para completarlo hacen falta la firma CMS —`cryptography` ya viene en el
extra— y un cliente SOAP. `pyafipws` es la referencia conocida en Python, con
licencia GPL.

## Antes de usarlo en producción

- El padrón tiene **límites diarios de consultas** por CUIT representada.
  Cachear resultados, no solo el ticket.
- Los certificados vencen. `cms.cert.expired` es un error del WSAA, y conviene
  enterarse antes de que pase.
- Usá primero homologación. Los endpoints y los DN de destino son distintos en
  cada ambiente, y confundirlos da errores que parecen de permisos.
- Nada de esto se probó contra ARCA. Probalo vos en homologación antes de
  confiarle un dato real.
