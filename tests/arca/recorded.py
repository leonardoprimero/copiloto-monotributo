"""Responses recorded from ARCA's homologación services on 2026-09-24.

The fixtures in `responses.py` come from the manual. These come from the
wire, and they disagree with the manual in two places that broke the client:

- WSAA does not answer with a `loginTicketResponse`. It answers with a SOAP
  envelope whose `loginCmsReturn` carries that document as escaped text.
- A CUIT that does not exist is a SOAP fault, not an `errorConstancia`. An
  `errorConstancia` is what a CUIT that exists but cannot be certified gets:
  cancelled, or blocked until its owner registers biometric data.

Edits, and nothing else: the token and sign are replaced (they were live
credentials), and the certificate's CUIT in `destination` is replaced by a
synthetic one. The padrón responses describe fictional people in ARCA's
test database and are verbatim.
"""

# loginCms, answered by wsaahomo.afip.gov.ar.
LOGIN_CMS_RESPONSE = """<?xml version="1.0" encoding="UTF-8"?><soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><soapenv:Body><loginCmsResponse xmlns="http://wsaa.view.sua.dvadac.desein.afip.gov"><loginCmsReturn>&lt;?xml version=&quot;1.0&quot; encoding=&quot;UTF-8&quot; standalone=&quot;yes&quot;?&gt;
&lt;loginTicketResponse version=&quot;1.0&quot;&gt;
    &lt;header&gt;
        &lt;source&gt;CN=wsaahomo, O=AFIP, C=AR, SERIALNUMBER=CUIT 33693450239&lt;/source&gt;
        &lt;destination&gt;SERIALNUMBER=CUIT 20111111112, CN=copilotohomo&lt;/destination&gt;
        &lt;uniqueId&gt;3076468954&lt;/uniqueId&gt;
        &lt;generationTime&gt;2026-09-24T17:52:18.990-03:00&lt;/generationTime&gt;
        &lt;expirationTime&gt;2026-09-25T05:52:18.990-03:00&lt;/expirationTime&gt;
    &lt;/header&gt;
    &lt;credentials&gt;
        &lt;token&gt;PD94bWwgdG9rZW4tcmVkYWN0ZWQ=&lt;/token&gt;
        &lt;sign&gt;c2lnbi1yZWRhY3RlZA==&lt;/sign&gt;
    &lt;/credentials&gt;
&lt;/loginTicketResponse&gt;
</loginCmsReturn></loginCmsResponse></soapenv:Body></soapenv:Envelope>"""

LOGIN_TOKEN = "PD94bWwgdG9rZW4tcmVkYWN0ZWQ="  # noqa: S105
LOGIN_SIGN = "c2lnbi1yZWRhY3RlZA=="
LOGIN_EXPIRES = "2026-09-25T05:52:18.990-03:00"

# getPersona_v2 for 27015942210, a monotributista in category B.
PERSONA_MONOTRIBUTISTA = """<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"><soap:Body><ns2:getPersona_v2Response xmlns:ns2="http://a5.soap.ws.server.puc.sr/"><personaReturn><datosGenerales><apellido>INTENTAR</apellido><caracterizacion><descripcionCaracterizacion>CUENTA CORRIENTE</descripcionCaracterizacion><fechaSolicitud>20070901</fechaSolicitud><idCaracterizacion>82</idCaracterizacion><periodo>20070901</periodo></caracterizacion><caracterizacion><descripcionCaracterizacion>CATEGORÍA A: MUY BAJO RIESGO</descripcionCaracterizacion><fechaSolicitud>20161025</fechaSolicitud><idCaracterizacion>354</idCaracterizacion><periodo>20161025</periodo></caracterizacion><domicilioFiscal><codPostal>5881</codPostal><descripcionProvincia>SAN LUIS</descripcionProvincia><direccion>AV LOS INCAS 4137</direccion><idProvincia>11</idProvincia><localidad>MERLO</localidad><tipoDomicilio>FISCAL</tipoDomicilio></domicilioFiscal><esSucesion>NO</esSucesion><estadoClave>ACTIVO</estadoClave><idPersona>27015942210</idPersona><mesCierre>12</mesCierre><nombre>JAZMIN</nombre><tipoClave>CUIT</tipoClave><tipoPersona>FISICA</tipoPersona></datosGenerales><datosMonotributo><actividad><descripcionActividad>ALQUILER DE EFECTOS PERSONALES Y ENSERES DOMÉSTICOS N.C.P.</descripcionActividad><idActividad>772099</idActividad><nomenclador>883</nomenclador><orden>1</orden><periodo>201706</periodo></actividad><actividadMonotributista><descripcionActividad>ALQUILER DE EFECTOS PERSONALES Y ENSERES DOMÉSTICOS N.C.P.</descripcionActividad><idActividad>772099</idActividad><nomenclador>883</nomenclador><orden>1</orden><periodo>201706</periodo></actividadMonotributista><categoriaMonotributo><descripcionCategoria>B LOCACIONES DE SERVICIOS</descripcionCategoria><idCategoria>36</idCategoria><idImpuesto>20</idImpuesto><periodo>201804</periodo></categoriaMonotributo><impuesto><descripcionImpuesto>MONOTRIBUTO</descripcionImpuesto><estadoImpuesto>AC</estadoImpuesto><idImpuesto>20</idImpuesto><motivo>INSCRIPCIÓN NO TRAMITADA EN AGENCIA</motivo><periodo>201803</periodo></impuesto></datosMonotributo><datosRegimenGeneral><actividad><descripcionActividad>ALQUILER DE EFECTOS PERSONALES Y ENSERES DOMÉSTICOS N.C.P.</descripcionActividad><idActividad>772099</idActividad><nomenclador>883</nomenclador><orden>1</orden><periodo>201706</periodo></actividad><impuesto><descripcionImpuesto>GANANCIAS PERSONAS FISICAS</descripcionImpuesto><estadoImpuesto>AC</estadoImpuesto><idImpuesto>11</idImpuesto><motivo>INSCRIPCIÓN TRAMITADA EN AGENCIA</motivo><periodo>202501</periodo></impuesto><impuesto><descripcionImpuesto>EMPLEADOR-APORTES SEG. SOCIAL</descripcionImpuesto><estadoImpuesto>AC</estadoImpuesto><idImpuesto>301</idImpuesto><motivo>INSCRIPCIÓN NO TRAMITADA EN AGENCIA</motivo><periodo>200004</periodo></impuesto></datosRegimenGeneral><metadata><fechaHora>2026-09-24T17:52:44.010-03:00</fechaHora><servidor>setiwsh2</servidor></metadata></personaReturn></ns2:getPersona_v2Response></soap:Body></soap:Envelope>"""

# getPersona_v2 for 20000000516: the CUIT exists, the constancia is blocked.
PERSONA_BLOCKED = """<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"><soap:Body><ns2:getPersona_v2Response xmlns:ns2="http://a5.soap.ws.server.puc.sr/"><personaReturn><errorConstancia><apellido>ERNESTO DANIEL</apellido><error>La CUIT fue cancelada de acuerdo a: DOMICILIO FISCAL ELECTRÓNICO NO CONSTITUIDO RG 4280.</error><error>La CUIT registra pendiente la constitución del domicilio fiscal electrónico de acuerdo a lo normado en la RG 4280/18 AFIP.</error><error>La constancia de inscripción se encuentra bloqueada porque el contribuyente, o su Administrador de Relaciones, no registró los datos biométricos. Puede hacerlo desde la aplicación Mi AFIP, o en una dependencia de ARCA con un turno previo.</error><idPersona>20000000516</idPersona><nombre>MARCELO NICOLAS</nombre></errorConstancia><metadata><fechaHora>2026-09-24T17:52:44.363-03:00</fechaHora><servidor>setiwsh2</servidor></metadata></personaReturn></ns2:getPersona_v2Response></soap:Body></soap:Envelope>"""

# getPersona_v2 for a CUIT missing from the test database: the faultstring of
# the SOAP fault ARCA answered with, which is what reaches this code.
PERSONA_NOT_FOUND_FAULT = "No existe persona con ese Id"
