"""Response fixtures shared by the padrón tests.

Every string below is copied from ARCA's manual for developers of
`ws_sr_constancia_inscripcion`, version 3.4 (08/05/23), trimmed to the parts
this copilot reads. They live here rather than in a test module so both the
parser tests and the registry tests use the same documented responses.
"""

# From section 3.3.3, the getPersonaList_v2 example: a monotributista.
MONOTRIBUTISTA = """<?xml version="1.0"?>
<personaReturn>
  <datosGenerales>
    <apellido>JAZMIN</apellido>
    <estadoClave>ACTIVO</estadoClave>
    <idPersona>27015942210</idPersona>
    <nombre>JAZMIN</nombre>
    <tipoClave>CUIT</tipoClave>
    <tipoPersona>FISICA</tipoPersona>
  </datosGenerales>
  <datosMonotributo>
    <actividadMonotributista>
      <descripcionActividad>PREST. DE SERVICIO O LOCACION</descripcionActividad>
      <idActividad>8</idActividad>
    </actividadMonotributista>
    <categoriaMonotributo>
      <descripcionCategoria>B LOCACIONES DE SERVICIO</descripcionCategoria>
      <idCategoria>36</idCategoria>
      <idImpuesto>20</idImpuesto>
      <periodo>201804</periodo>
    </categoriaMonotributo>
    <impuesto>
      <descripcionImpuesto>MONOTRIBUTO</descripcionImpuesto>
      <idImpuesto>20</idImpuesto>
    </impuesto>
  </datosMonotributo>
</personaReturn>"""

# From section 3.2.3: a taxpayer with datosRegimenGeneral and no monotributo.
REGIMEN_GENERAL = """<?xml version="1.0"?>
<personaReturn>
  <datosGenerales>
    <apellido>MICHELLE ELIZABETH</apellido>
    <estadoClave>ACTIVO</estadoClave>
    <idPersona>20201731594</idPersona>
    <nombre>FELIX</nombre>
    <tipoClave>CUIT</tipoClave>
    <tipoPersona>FISICA</tipoPersona>
  </datosGenerales>
  <datosRegimenGeneral>
    <impuesto>
      <descripcionImpuesto>DERECHO ESPECIFICO</descripcionImpuesto>
      <idImpuesto>2015</idImpuesto>
    </impuesto>
  </datosRegimenGeneral>
</personaReturn>"""

# From section 3.3.3: the CUIT that does not exist.
NO_EXISTE = """<?xml version="1.0"?>
<personaReturn>
  <errorConstancia>
    <error>No existe persona con ese Id</error>
    <idPersona>12345678901</idPersona>
  </errorConstancia>
</personaReturn>"""

JURIDICA = """<?xml version="1.0"?>
<personaReturn>
  <datosGenerales>
    <estadoClave>ACTIVO</estadoClave>
    <idPersona>30500010912</idPersona>
    <razonSocial>UNA SOCIEDAD SA</razonSocial>
    <tipoClave>CUIT</tipoClave>
    <tipoPersona>JURIDICA</tipoPersona>
  </datosGenerales>
  <datosMonotributo>
    <categoriaMonotributo>
      <descripcionCategoria>D LOCACIONES DE SERVICIO</descripcionCategoria>
      <idCategoria>38</idCategoria>
    </categoriaMonotributo>
  </datosMonotributo>
</personaReturn>"""
