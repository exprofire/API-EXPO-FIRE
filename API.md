# API Documentation - Sistema de Gestión de Extintores

> Documentación completa de los endpoints REST API

---

## ✅ Estado de la API

**Todos los endpoints están COMPLETAMENTE IMPLEMENTADOS y FUNCIONANDO.**

| Estado | Descripción |
|--------|-------------|
| ✅ Implementado | Endpoint funcionando y probado |
| 🧪 Testing | Usar en desarrollo, no en producción |
| 📝 Documentado | Documentación completa disponible |

**Última actualización:** 13 de Enero, 2026  
**Versión:** 1.0 - Production Ready

---

## 📋 Índice

- [Introducción](#introducción)
- [Autenticación](#autenticación)
- [Endpoints de Autenticación](#endpoints-de-autenticación)
- [Endpoints de Extintores](#endpoints-de-extintores)
- [Endpoints Públicos (QR)](#endpoints-públicos-qr)
- [Códigos de Estado](#códigos-de-estado)
- [Manejo de Errores](#manejo-de-errores)
- [Ejemplos de Uso](#ejemplos-de-uso)

---

## 🌐 Introducción

### Base URL

**Desarrollo:** `http://localhost:8000`

**Producción:** `https://tu-dominio.com`

> Nota: en este proyecto los recursos principales viven en rutas directas (ej. `/extintores/`, `/empresas/`, `/usuarios/`).  
> Las rutas de autenticación JWT viven bajo el prefijo `/api/*` (ej. `/api/token/`, `/api/token/refresh/`, `/api/perfil/`).

### Formato de Datos

Todos los endpoints aceptan y retornan datos en formato **JSON**.

**Headers requeridos:**

```http
Content-Type: application/json
Accept: application/json
```

### Versionado

Actualmente en **v1** (sin prefijo en la URL por ahora).

---

## 🔐 Autenticación

### Método de Autenticación

El sistema utiliza **JWT (SimpleJWT)**.

### Cómo Autenticarse

1. Obtener tokens mediante el endpoint `POST /api/token/` (retorna `access` y `refresh`)
2. Incluir el token `access` en el header `Authorization` de las peticiones:

```http
Authorization: Bearer <access_token>
```

### Endpoints Protegidos

Los endpoints que requieren autenticación están marcados con 🔒.

---

## 🔑 Endpoints de Autenticación

**Estado:** ✅ JWT Authentication completamente configurado con SimpleJWT

### Login ✅ Implementado

Autenticar usuario y obtener token.

```http
POST /api/token/
```

**Autenticación requerida:** ❌ No  
**Implementación:** JWT (Simple JWT) configurado en [`backend/core/settings.py`](backend/core/settings.py)

**Body Parameters:**

| Campo | Tipo | Requerido | Descripción |
|-------|------|-----------|-------------|
| `username` | string | Sí | Nombre de usuario |
| `password` | string | Sí | Contraseña |

**Ejemplo Request:**

```bash
curl -X POST http://localhost:8000/api/token/ \
  -H "Content-Type: application/json" \
  -d '{
    "username": "admin",
    "password": "password123"
  }'
```

**Ejemplo Response (200 OK):**

```json
{
  "refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9....",
  "access": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...."
}
```

**Errores Posibles:**

| Código | Descripción |
|--------|-------------|
| 400 | Credenciales inválidas o campos faltantes |
| 401 | Usuario o contraseña incorrectos |

---

### Logout (cliente)

No hay un endpoint dedicado de logout. Para “cerrar sesión”, el cliente debe borrar el `access`/`refresh` almacenado (por ejemplo en `localStorage`) y, si aplica, invalidar su sesión del navegador si usas `SessionAuthentication`.

---

### Obtener Perfil Actual ✅ Implementado

Obtener información del perfil del usuario autenticado (y crearlo si aún no existe).

```http
GET /api/perfil/
```

**Autenticación requerida:** 🔒 Sí

**Headers:**

```http
Authorization: Bearer <access_token>
```

**Ejemplo Request:**

```bash
curl -X GET http://localhost:8000/api/perfil/ \
  -H "Authorization: Bearer <access_token>"
```

---

## 🧯 Endpoints de Extintores

**Estado:** ✅ Todos los endpoints implementados y funcionando  
**Código:** [`backend/extintores/views.py`](backend/extintores/views.py) - `ExtintorViewSet`

### Listar Extintores ✅ Implementado

Obtener lista de todos los extintores con filtros opcionales.

```http
GET /extintores/
```

**Autenticación requerida:** 🔒 Sí  
**ViewSet:** ExtintorViewSet.list() con paginación automática

**Query Parameters:**

| Parámetro | Tipo | Descripción | Ejemplo |
|-----------|------|-------------|---------|
| `estado` | string | Filtrar por estado (verde, amarillo, rojo) | `?estado=rojo` |
| `tipo` | string | Filtrar por tipo de extintor | `?tipo=CO2` |
| `ubicacion` | string | Buscar por ubicación (contiene) | `?ubicacion=planta` |
| `codigo` | string | Buscar por código | `?codigo=EXT-001` |
| `page` | integer | Número de página para paginación | `?page=2` |
| `page_size` | integer | Cantidad de resultados por página | `?page_size=20` |
| `ordering` | string | Ordenar por campo | `?ordering=-fecha_vencimiento` |

**Ejemplo Request:**

```bash
curl -X GET "http://localhost:8000/extintores/?estado=rojo&page=1" \
  -H "Authorization: Bearer <access_token>"
```

**Ejemplo Response (200 OK):**

```json
{
  "count": 45,
  "next": "http://localhost:8000/extintores/?page=2",
  "previous": null,
  "results": [
    {
      "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "codigo": "EXT-001",
      "ubicacion": "Planta Baja - Pasillo A",
      "tipo": "CO2",
      "capacidad": "5kg",
      "fecha_fabricacion": "2022-01-15",
      "fecha_vencimiento": "2027-01-15",
      "fecha_ultima_revision": "2025-06-10",
      "fecha_proxima_revision": "2026-06-10",
      "estado": "verde",
      "observaciones": "En buen estado",
      "qr_code": "http://localhost:8000/media/qr_codes/EXT-001.png",
      "created_at": "2025-01-01T10:00:00Z",
      "updated_at": "2025-12-20T15:30:00Z"
    },
    {
      "id": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
      "codigo": "EXT-002",
      "ubicacion": "Planta Alta - Oficina 3",
      "tipo": "PQS",
      "capacidad": "6kg",
      "fecha_fabricacion": "2021-03-20",
      "fecha_vencimiento": "2026-03-20",
      "fecha_ultima_revision": "2024-08-15",
      "fecha_proxima_revision": "2025-08-15",
      "estado": "rojo",
      "observaciones": "Requiere revisión urgente",
      "qr_code": "http://localhost:8000/media/qr_codes/EXT-002.png",
      "created_at": "2025-01-05T11:00:00Z",
      "updated_at": "2025-12-22T09:15:00Z"
    }
  ]
}
```

---

### Obtener Extintor por ID ✅ Implementado

Obtener detalles completos de un extintor específico.

```http
GET /extintores/{id}/
```

**Autenticación requerida:** 🔒 Sí  
**ViewSet:** ExtintorViewSet.retrieve()

**Path Parameters:**

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `id` | UUID | ID único del extintor |

**Ejemplo Request:**

```bash
curl -X GET http://localhost:8000/extintores/a1b2c3d4-e5f6-7890-abcd-ef1234567890/ \
  -H "Authorization: Bearer <access_token>"
```

**Ejemplo Response (200 OK):**

```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "codigo": "EXT-001",
  "ubicacion": "Planta Baja - Pasillo A",
  "tipo": "CO2",
  "capacidad": "5kg",
  "fecha_fabricacion": "2022-01-15",
  "fecha_vencimiento": "2027-01-15",
  "fecha_ultima_revision": "2025-06-10",
  "fecha_proxima_revision": "2026-06-10",
  "estado": "verde",
  "observaciones": "En buen estado",
  "qr_code": "http://localhost:8000/media/qr_codes/EXT-001.png",
  "created_at": "2025-01-01T10:00:00Z",
  "updated_at": "2025-12-20T15:30:00Z"
}
```

**Errores Posibles:**

| Código | Descripción |
|--------|-------------|
| 404 | Extintor no encontrado |

---

### Crear Extintor ✅ Implementado

Crear un nuevo extintor en el sistema.

```http
POST /extintores/
```

**Autenticación requerida:** 🔒 Sí  
**ViewSet:** ExtintorViewSet.create()  
**Serializador:** ExtintorCreateSerializer con validaciones  
**Característica:** El QR code se genera automáticamente al crear

**Body Parameters:**

| Campo | Tipo | Requerido | Descripción |
|-------|------|-----------|-------------|
| `codigo` | string | Sí | Código único del extintor |
| `ubicacion` | string | Sí | Ubicación física |
| `tipo` | string | Sí | Agente extintor (PQS_ABC, PQS_BC, CO2, AGUA, ESPUMA, HALOTRON, ACETATO_K) |
| `capacidad` | string | Sí | Capacidad (ej: "5kg", "10lb") |
| `fecha_fabricacion` | date | Sí | Fecha de fabricación (YYYY-MM-DD) |
| `fecha_vencimiento` | date | Sí | Fecha de vencimiento |
| `fecha_ultima_revision` | date | No | Fecha de última revisión |
| `fecha_proxima_revision` | date | Sí | Fecha de próxima revisión |
| `observaciones` | string | No | Observaciones adicionales |

**Ejemplo Request:**

```bash
curl -X POST http://localhost:8000/extintores/ \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "codigo": "EXT-003",
    "ubicacion": "Bodega - Sector B",
    "tipo": "PQS_ABC",
    "capacidad": "10kg",
    "fecha_fabricacion": "2023-05-10",
    "fecha_vencimiento": "2028-05-10",
    "fecha_ultima_revision": "2025-11-20",
    "fecha_proxima_revision": "2026-11-20",
    "observaciones": "Nuevo extintor instalado"
  }'
```

**Ejemplo Response (201 Created):**

```json
{
  "id": "c3d4e5f6-a7b8-9012-cdef-123456789012",
  "codigo": "EXT-003",
  "ubicacion": "Bodega - Sector B",
  "tipo": "PQS_ABC",
  "capacidad": "10kg",
  "fecha_fabricacion": "2023-05-10",
  "fecha_vencimiento": "2028-05-10",
  "fecha_ultima_revision": "2025-11-20",
  "fecha_proxima_revision": "2026-11-20",
  "estado": "verde",
  "observaciones": "Nuevo extintor instalado",
  "qr_code": "http://localhost:8000/media/qr_codes/EXT-003.png",
  "created_at": "2026-01-09T14:30:00Z",
  "updated_at": "2026-01-09T14:30:00Z"
}
```

**Errores Posibles:**

| Código | Descripción |
|--------|-------------|
| 400 | Datos inválidos o código duplicado |
| 401 | No autenticado |

**Notas:**
- El código QR se genera automáticamente al crear el extintor
- El campo `estado` se calcula automáticamente según las fechas

---

### Actualizar Extintor ✅ Implementado

Actualizar parcial o totalmente un extintor existente.

```http
PATCH /extintores/{id}/
PUT /extintores/{id}/
```

**Autenticación requerida:** 🔒 Sí  
**ViewSet:** ExtintorViewSet.update() y ExtintorViewSet.partial_update()

**Path Parameters:**

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `id` | UUID | ID único del extintor |

**Body Parameters:** (Mismos campos que crear, todos opcionales para PATCH)

**Ejemplo Request (PATCH):**

```bash
curl -X PATCH http://localhost:8000/extintores/a1b2c3d4-e5f6-7890-abcd-ef1234567890/ \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "ubicacion": "Planta Baja - Pasillo B",
    "observaciones": "Reubicado por remodelación"
  }'
```

**Ejemplo Response (200 OK):**

```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "codigo": "EXT-001",
  "ubicacion": "Planta Baja - Pasillo B",
  "tipo": "CO2",
  "capacidad": "5kg",
  "fecha_fabricacion": "2022-01-15",
  "fecha_vencimiento": "2027-01-15",
  "fecha_ultima_revision": "2025-06-10",
  "fecha_proxima_revision": "2026-06-10",
  "estado": "verde",
  "observaciones": "Reubicado por remodelación",
  "qr_code": "http://localhost:8000/media/qr_codes/EXT-001.png",
  "created_at": "2025-01-01T10:00:00Z",
  "updated_at": "2026-01-09T15:45:00Z"
}
```

**Errores Posibles:**

| Código | Descripción |
|--------|-------------|
| 400 | Datos inválidos |
| 404 | Extintor no encontrado |

---

### Eliminar Extintor ✅ Implementado

Eliminar un extintor del sistema.

```http
DELETE /extintores/{id}/
```

**Autenticación requerida:** 🔒 Sí  
**ViewSet:** ExtintorViewSet.destroy()

**Path Parameters:**

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `id` | UUID | ID único del extintor |

**Ejemplo Request:**

```bash
curl -X DELETE http://localhost:8000/extintores/a1b2c3d4-e5f6-7890-abcd-ef1234567890/ \
  -H "Authorization: Bearer <access_token>"
```

**Ejemplo Response (204 No Content):**

```
(Sin contenido)
```

**Errores Posibles:**

| Código | Descripción |
|--------|-------------|
| 404 | Extintor no encontrado |

---

### Obtener Etiqueta QR (PNG) ✅ Implementado

Descargar o visualizar la **etiqueta** lista para imprimir (QR + datos del extintor).

```http
GET /extintores/{id}/etiqueta/
```

**Autenticación requerida:** 🔒 Sí

**Path Parameters:**

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `id` | UUID | ID único del extintor |

**Ejemplo Request:**

```bash
curl -X GET http://localhost:8000/extintores/a1b2c3d4-e5f6-7890-abcd-ef1234567890/etiqueta/ \
  -H "Authorization: Bearer <access_token>" \
  -o extintor_qr.png
```

**Ejemplo Response:**

```
(Imagen PNG del código QR)
```

**Notas:**
- Response es una imagen PNG
- Content-Type: `image/png`
- Puede abrirse directamente en el navegador

---

### Obtener Estadísticas ✅ Implementado

Obtener estadísticas generales de los extintores.

```http
GET /extintores/estadisticas/
```

**Autenticación requerida:** 🔒 Sí  
**ViewSet:** ExtintorViewSet.estadisticas() - Custom action  
**Implementación:** Líneas 81-108 en `views.py`

**Ejemplo Request:**

```bash
curl -X GET http://localhost:8000/extintores/estadisticas/ \
  -H "Authorization: Bearer <access_token>"
```

**Ejemplo Response (200 OK):**

```json
{
  "total": 45,
  "por_estado": {
    "verde": 30,
    "amarillo": 10,
    "rojo": 5
  },
  "por_tipo": {
    "CO2": 15,
    "PQS": 20,
    "ABC": 10
  },
  "proximos_vencimientos": [
    {
      "id": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
      "codigo": "EXT-002",
      "ubicacion": "Planta Alta - Oficina 3",
      "fecha_proxima_revision": "2026-02-15",
      "dias_restantes": 37
    }
  ]
}
```

---

## 📝 Endpoints de Formularios Dinámicos

### Obtener plantilla activa por código

```http
GET /api/forms/templates/UIPC_SEH/activo/
```

**Autenticación requerida:** 🔒 Sí  
**Descripción:** Devuelve la plantilla activa (`activo=True`) con sus preguntas completas para renderizar el formulario en front.
Ahora valida permisos por rol/empresa. Si el usuario no tiene acceso, responde `403`.

**Query params opcionales:**
- `empresa_id`: fuerza evaluación de permisos por esa empresa.

Cada pregunta incluye:

- `orden`: se usa para ordenar visualmente el formulario; renderiza preguntas en ese orden ascendente.  
- `tipo`: define qué control mostrar (`booleano` → checkbox/toggle; `texto` → textarea/input; `numero` → input type=number; `seleccion`/`multiseleccion` → select/radio/checkbox; `fecha` → date picker; `archivo` → uploader).  
- `ayuda`: texto opcional que puedes colocar como subtítulo/info adicional debajo del label.  
- `reglas_visibilidad`: lista de condiciones `{"campo":"clave","operador":"==","valor":...}`; evalúalas contra los valores cargados hasta el momento y oculta la pregunta si no se cumple la condición.  
- `reglas_validacion`: complementa `requerido` (por ejemplo `{"requerido_si":{"campo":"danos_cilindro","operador":"==","valor":true},"min_longitud":5}`) y debe ejecutarse antes de enviar, añadiendo mensajes en español.  
- `opciones`: solo para `seleccion`/`multiseleccion`; muestra cada opción con `valor` (clave persistente) y `etiqueta` (texto visible). El campo `orden` dentro de opciones controla su orden.

**Ejemplo parcial de pregunta (GET /api/forms/templates/GRADO_RIESGO_ANGRI/activo/):**

```json
{
  "clave": "en_establecimiento",
  "etiqueta": "¿Te encuentras en el establecimiento?",
  "tipo": "seleccion",
  "requerido": true,
  "orden": 1,
  "ayuda": "Responde con la opción que corresponda.",
  "reglas_visibilidad": {},
  "reglas_validacion": {},
  "opciones": [
    {"valor": "si", "etiqueta": "Sí (iniciar recorrido)", "orden": 1},
    {"valor": "no", "etiqueta": "No (proporcionar datos de quién refiere)", "orden": 2}
  ]
}
```

Usa `orden` para dibujar preguntas en el mismo orden que el backend las definió y respeta los tipos al elegir componentes en el frontend. Aplica `reglas_visibilidad` por cada valor – si una pregunta no aplica no debe mostrarse ni enviarse – y usa `reglas_validacion` junto con `requerido` para validar antes de enviar.

### Listar todas las plantillas disponibles

```http
GET /api/forms/templates/
```

**Autenticación requerida:** 🔒 Sí  
**Descripción:** Retorna plantillas (activa/inactiva) con preguntas y reglas.

**Query params:**
- `disponibles=true`: devuelve solo plantillas permitidas para el usuario autenticado.
- `empresa_id`: usado junto con `disponibles=true` para filtrar por permisos de una empresa concreta.

**Ejemplo Response (200 OK):**

```json
[
  {
    "id": 1,
    "codigo": "GRADO_RIESGO_ANGRI",
    "titulo": "Grado de Riesgo de Incendio ANGRI",
    "version": 1,
    "activo": true,
    "descripcion": "Cuestionario para levantar el riesgo de incendio en campo.",
    "roles_permitidos": ["SUPERADMIN", "ANALISTA"],
    "empresas_permitidas": [1, 3],
    "preguntas": [ ... ],
  }
]
```

### Crear o versionar un template

```http
POST /api/forms/templates/
```

**Autenticación requerida:** 🔒 Sí  
**Descripción:** Crea o versiona una plantilla. Si marcas `activo: true`, el backend desactiva cualquier versión anterior del mismo código.

**Campos nuevos de permisos:**
- `roles_permitidos`: lista de roles permitidos. Vacío (`[]`) = todos los roles.
- `empresas_permitidas`: lista de IDs de empresa permitidas. Vacío (`[]`) = todas las empresas.

**Ejemplo Request (simplificado):**

```json
{
  "codigo": "GRADO_RIESGO_ANGRI",
  "titulo": "Grado de Riesgo de Incendio ANGRI",
  "version": 2,
  "activo": true,
  "descripcion": "Cuestionario actualizado",
  "roles_permitidos": ["SUPERADMIN", "SUPERVISOR"],
  "empresas_permitidas": [1, 2],
  "preguntas": [ ... ]
}
```

**Respuesta (201 Created):** Devuelve la plantilla recién creada con todas sus preguntas y opciones, igual que el GET.

**Ejemplos rápidos de alcance:**
- Para todos: `roles_permitidos: []` y `empresas_permitidas: []`
- Solo por roles: `roles_permitidos: ["ANALISTA"]`, `empresas_permitidas: []`
- Solo por empresas: `roles_permitidos: []`, `empresas_permitidas: [5, 8]`
- Mixto: `roles_permitidos: ["SUPERADMIN"]`, `empresas_permitidas: [1]`

### Ejemplo de uso del template en front

1. **Descarga el template activo** (`GET /api/forms/templates/<codigo>/activo/`).  
2. **Ordena las preguntas** usando `orden`: genera una lista antes de renderizar.  
3. Para cada pregunta, **elige el control** según `tipo` y añade el texto `etiqueta` como label y `ayuda` como subtítulo (si no está vacío).  
4. Si la pregunta tiene `opciones`, márcalas y respeta el `orden` de cada opción para mostrarlas en el mismo orden que el backend espera.  
5. Evalúa `reglas_visibilidad` en tiempo real (por ejemplo, si un valor de `agente_extintor` no cumple, oculta la pregunta y no envíes esa clave).  
6. Antes de enviar, verifica `requerido` y aplica `reglas_validacion` (como `requerido_si` o `min_longitud`), retornando mensajes en español del lado del cliente para tener UX consistente.  
7. Arma el payload `respuestas_json` con las claves definidas en `clave` y los valores validados y manda `POST /api/forms/runs/` (o `PATCH` si actualizas) incluyendo `template`, `empresa`, `scope_type`, `scope_id` y `respuestas_json`.

### Contactos vinculados a empresa/extintor

Los contactos (`empresas.Contacto`) almacenan el nombre/cargo, dos correos y dos teléfonos más el domicilio del responsable que recibe al técnico. Cada contacto:

- Pertenece a una `empresa` obligatoria (`ForeignKey`).  
- Puede vincular opcionalmente a un `extintor` para filtrar por ubicación.  
- Guarda `nombre`, `cargo`, `correo_principal`, `correo_secundario`, `telefono_principal`, `telefono_secundario` y `domicilio`.  
- Está disponible en Django Admin bajo la sección “Contactos” para crear/editar y revisar quién recibe cada visita.

Utiliza este modelo para cubrir la necesidad de “Nombre y cargo de quien recibe” y “2 correos, 2 teléfonos y domicilio”; si necesitas exponerlo vía API, puedes crear un ViewSet similar que liste `empresas.Contacto` y lo filtre por empresa/extintor.

### CRUD de ejecuciones (`FormRun`)

```http
POST /api/forms/runs/
```

**Ejemplo request (creación en borrador):**

```json
{
  "template": 1,
  "empresa": 1,
  "scope_type": "extintor",
  "scope_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "tipo_servicio": "mantenimiento",
  "estado": "borrador",
  "respuestas_json": {
    "ubicacion_correcta": true,
    "danos_cilindro": false,
    "agente_extintor": "PQS"
  }
}
```

**Respuesta (201 Created):**

```json
{
  "id": 12,
  "template": 1,
  "empresa": 1,
  "tecnico": 3,
  "estado": "borrador",
  "scope_type": "extintor",
  "scope_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "tipo_servicio": "mantenimiento",
  "respuestas_json": {
    "ubicacion_correcta": true,
    "danos_cilindro": false,
    "agente_extintor": "PQS"
  },
  "tiene_incidencias": false,
  "creado_en": "2026-02-04T05:00:00Z",
  "actualizado_en": "2026-02-04T05:00:00Z"
}
```

**Actualizar ejecución (completar el formulario):**

```http
PATCH /api/forms/runs/12/
```

```json
{
  "estado": "completado",
  "respuestas_json": {
    "presion_optima": true,
    "danos_cilindro": false,
    "danos_cilindro_descripcion": "",
    "vigente_mantenimiento_recarga": true
  }
}
```

Si se omiten respuestas requeridas (por ejemplo `presion_optima` o `danos_cilindro_descripcion` cuando aplica), la API devuelve `400 Bad Request` con un detalle en `respuestas_json`.
Si la plantilla no está permitida para el rol/empresa del usuario, devuelve `400` con error en `template`.

**Listado filtrado:**

```http
GET /api/forms/runs/?scope_type=extintor&scope_id=a1b2c3d4-e5f6-7890-abcd-ef1234567890&codigo=UIPC_SEH&estado=borrador
```

La misma vista soporta `GET /api/forms/runs/<id>/` para obtener una ejecución individual.


---
## 📱 Endpoints Públicos (QR)

**Estado:** ✅ Endpoint público implementado para escaneo de QR

### Ver Extintor por Código QR ✅ Implementado

Vista pública de un extintor mediante su **código** (pensado para escaneo QR).

```http
GET /extintores/por-codigo/{codigo}/
```

**Autenticación requerida:** ❌ No (público)  
**ViewSet:** ExtintorViewSet.por_codigo() - Custom action  
**Implementación:** ver `backend/extintores/views.py`  
**Permisos:** AllowAny - diseñado para QR scanner

**Path Parameters:**

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `codigo` | string | Código único del extintor (ej: EXT-001) |

**Ejemplo Request:**

```bash
curl -X GET http://localhost:8000/extintores/por-codigo/EXT-001/
```

**Ejemplo Response (200 OK):**

```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "codigo": "EXT-001",
  "ubicacion": "Planta Baja - Pasillo A",
  "tipo": "CO2",
  "estado": "verde",
  "fecha_proxima_revision": "2026-06-10",
  "observaciones": "En buen estado"
}
```

**Errores Posibles:**

| Código | Descripción |
|--------|-------------|
| 404 | Código de extintor no encontrado |

**Notas:**
- Este endpoint es la URL que contiene el código QR
- Diseñado para ser escaneado desde móviles

---

## 📊 Códigos de Estado HTTP

| Código | Significado | Descripción |
|--------|-------------|-------------|
| 200 | OK | Petición exitosa |
| 201 | Created | Recurso creado exitosamente |
| 204 | No Content | Petición exitosa sin contenido (ej: DELETE) |
| 400 | Bad Request | Datos inválidos o faltantes |
| 401 | Unauthorized | No autenticado o token inválido |
| 403 | Forbidden | No autorizado (sin permisos) |
| 404 | Not Found | Recurso no encontrado |
| 500 | Internal Server Error | Error del servidor |

---

## ⚠️ Manejo de Errores

### Formato Estándar de Error

```json
{
  "detail": "Descripción del error en español",
  "code": "error_code",
  "field_errors": {
    "campo": ["Error específico del campo"]
  }
}
```

### Ejemplos de Errores Comunes

**400 - Validación:**

```json
{
  "codigo": ["Este campo ya existe."],
  "fecha_vencimiento": ["La fecha de vencimiento debe ser posterior a la fecha de fabricación."]
}
```

**401 - No Autenticado:**

```json
{
  "detail": "Authentication credentials were not provided."
}
```

**401 - Token Inválido:**

```json
{
  "detail": "Invalid token."
}
```

**404 - No Encontrado:**

```json
{
  "detail": "Not found."
}
```

---

## 💡 Ejemplos de Uso

### JavaScript (Axios)

```javascript
import axios from 'axios';

const API_URL = 'http://localhost:8000';

// Configurar axios con token
const api = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
  }
});

// Interceptor para agregar token
api.interceptors.request.use((config) => {
  const access = localStorage.getItem('access');
  if (access) {
    config.headers.Authorization = `Bearer ${access}`;
  }
  return config;
});

// Login
async function login(username, password) {
  const response = await api.post('/api/token/', {
    username,
    password
  });
  localStorage.setItem('access', response.data.access);
  localStorage.setItem('refresh', response.data.refresh);
  return response.data;
}

// Listar extintores
async function getExtintores(filters = {}) {
  const response = await api.get('/extintores/', { params: filters });
  return response.data;
}

// Crear extintor
async function createExtintor(data) {
  const response = await api.post('/extintores/', data);
  return response.data;
}

// Actualizar extintor
async function updateExtintor(id, data) {
  const response = await api.patch(`/extintores/${id}/`, data);
  return response.data;
}

// Eliminar extintor
async function deleteExtintor(id) {
  await api.delete(`/extintores/${id}/`);
}
```

### Python (requests)

```python
import requests

API_URL = 'http://localhost:8000'

class ExtintorAPI:
    def __init__(self):
        self.token = None
        self.session = requests.Session()
        
    def login(self, username, password):
        response = self.session.post(
            f'{API_URL}/api/token/',
            json={'username': username, 'password': password}
        )
        response.raise_for_status()
        self.token = response.json()['access']
        self.session.headers.update({
            'Authorization': f'Bearer {self.token}'
        })
        return response.json()
    
    def get_extintores(self, **filters):
        response = self.session.get(
            f'{API_URL}/extintores/',
            params=filters
        )
        response.raise_for_status()
        return response.json()
    
    def create_extintor(self, data):
        response = self.session.post(
            f'{API_URL}/extintores/',
            json=data
        )
        response.raise_for_status()
        return response.json()
    
    def update_extintor(self, extintor_id, data):
        response = self.session.patch(
            f'{API_URL}/extintores/{extintor_id}/',
            json=data
        )
        response.raise_for_status()
        return response.json()
    
    def delete_extintor(self, extintor_id):
        response = self.session.delete(
            f'{API_URL}/extintores/{extintor_id}/'
        )
        response.raise_for_status()

# Uso
api = ExtintorAPI()
api.login('admin', 'password123')
extintores = api.get_extintores(estado='rojo')
```

---

## 🧱 Cómo crear empresas, usuarios y descargar QR masivo

### Crear empresas y logos
- Endpoint: `POST /empresas/` (puedes usar Django Admin para uploads si prefieres GUI).
- Campos clave: `nombre` (string, obligatorio), `razon_social` (string, opcional) y `logo` (ImageField opcional).
- Para subir `logo` usa `multipart/form-data`; se almacena bajo `media/logos/` y el serializer retorna la URL pública.
- Response incluye `id`, `nombre`, `razon_social`, `logo` y `created_at`.

### Crear usuarios y perfiles con foto, teléfono y domicilio
- Endpoint: `POST /usuarios/` (requiere JWT de usuario admin). La vista usa `PerfilCreateSerializer` para crear `User` + `Perfil` en un mismo paso.
- Payload acepta `username`, `email`, `password`, `rol` (SUPERADMIN, ADMIN_EMPRESA, SUPERVISOR, ANALISTA) y `empresa_id` (UUID de `empresas`).
- Campos opcionales que puedes enviar en el mismo request: `telefono`, `domicilio` y `foto_perfil` (este último en `multipart/form-data`).
- Response devuelve el perfil completo con los datos de `user`, la empresa anidada, los nuevos campos de contacto y la URL de la foto.

### Impresión masiva de etiquetas QR
- Endpoint: `POST /extintores/impresionmasiva/` (JWT requerido).
- Body JSON obligatorio: `{ "ids": ["uuid1", "uuid2", ...] }`. Todos los IDs deben existir, de lo contrario devuelve 404 con `faltantes`.
- Respuesta: un ZIP (`Content-Type: application/zip`) con cada etiqueta PNG generada por `Extintor.obtener_etiqueta_png()` (QR + código + ubicación + capacidad + vencimiento).
- Usa este endpoint para generar paquetes listos para imprimir, en vez de pedir etiquetas individuales por extintor.

## 📚 Recursos Adicionales

- **[README.md](README.md)** - Documentación general del proyecto
- **[backend/README.md](backend/README.md)** - Configuración del backend
- **[ROADMAP.md](ROADMAP.md)** - Plan de desarrollo

---

## 🔄 Estado de Implementación

✅ **Todos los endpoints documentados están IMPLEMENTADOS y FUNCIONANDO.**

### Verificar Implementación

Para verificar que la API está funcionando:

1. **Iniciar servidor:**
   ```bash
   cd backend
   python manage.py runserver
   ```

2. **Probar endpoint:**
   ```bash
   curl http://localhost:8000/extintores/
   ```

3. **Ver en navegador:**
   - API Browsable: `http://localhost:8000/extintores/`
   - Django Admin: `http://localhost:8000/admin/`

### Código Fuente

| Componente | Archivo | Líneas |
|------------|---------|--------|
| ViewSet Principal | `backend/extintores/views.py` | - |
| Serializadores | `backend/extintores/serializers.py` | - |
| Modelo Extintor | `backend/extintores/models.py` | - |
| URLs | `backend/extintores/urls.py` | - |

### Testing

Puedes probar la API con:
- **Postman:** Importar endpoints y probar
- **Insomnia:** Similar a Postman
- **curl:** Desde línea de comandos
- **Browsable API:** Django REST Framework incluye interfaz web

**Guía rápida:** [`BACKEND_HANDOFF.md`](BACKEND_HANDOFF.md)

---

## 🔄 Actualización de Documentación

Esta documentación refleja el estado ACTUAL de la API implementada.

**Última actualización:** 02 de Febrero, 2026  
**Versión API:** v1.0 - Production Ready  
**Estado:** ✅ Completamente implementado

---

**¿Preguntas o problemas?** Consulta [`BACKEND_HANDOFF.md`](BACKEND_HANDOFF.md) para guía completa de setup.

## Carga masiva de extintores desde Excel

Estos endpoints requieren autenticación y solo están disponibles para `SUPERADMIN` (cualquier empresa) y `ADMIN_EMPRESA` (únicamente su empresa). La carga está limitada a 200 filas y archivos `.xlsx` de hasta 5 MB.

### Validar archivo

`POST /extintores/carga-masiva/validar/`

Recibe `multipart/form-data` con `empresa_id` y `archivo`. El archivo debe contener `Código`, `Ubicación`, `Agente`, `Modalidad`, `Capacidad`, `Fecha de fabricación` (opcional), `Fecha de mantenimiento`, `Fecha de vencimiento` y `Próxima revisión`.

No crea registros. Devuelve la empresa, el total, las filas válidas y las filas con errores:

```json
{
  "empresa": {"id": 1, "nombre": "Empresa"},
  "total": 2,
  "validas": [{"fila": 2, "datos": {"codigo": "EXT-001"}}],
  "con_error": [{"fila": 3, "datos": {"codigo": "EXT-002"}, "errores": [{"campo": "capacidad", "mensaje": "..."}]}]
}
```

### Confirmar carga

`POST /extintores/carga-masiva/confirmar/`

Recibe JSON con `empresa_id` y las filas corregidas. El servidor revalida todo, incluyendo duplicados dentro de la solicitud y contra la empresa seleccionada. Si alguna fila es inválida, no se crea ninguna. Si todas son válidas, cada extintor se guarda individualmente dentro de una transacción para generar su QR.

```json
{
  "empresa_id": 1,
  "filas": [{
    "codigo": "EXT-001",
    "ubicacion": "Pasillo principal",
    "tipo": "PQS_ABC",
    "modalidad": "portatil",
    "capacidad": "10 kg",
    "fecha_fabricacion": "2024-01-15",
    "ultima_revision": "2026-01-10",
    "fecha_vencimiento": "2028-01-10",
    "proxima_revision": "2026-07-10"
  }]
}
```

Respuesta exitosa:

```json
{"creados": 1, "extintores": [{"id": "uuid", "codigo": "EXT-001"}]}
```
