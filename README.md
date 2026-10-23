# Ejemplo 03: DRF

Aplicación de actividades e inscripciones: API en Django REST Framework, frontend en React y PostgreSQL, ejecutados con Docker Compose. La identidad del participante se determina con **autenticación JWT** (access token breve + refresh token en cookie `HttpOnly`). La API expone dos versiones convivientes (`v1` y `v2`), correlación de requests con `X-Correlation-ID` y logs estructurados en JSON. El contrato de errores, las reglas de cupo y la idempotencia de `PUT` y `DELETE` son los del Hito 1 y no cambian.

El repositorio contiene dos aplicaciones:

- `backend/`: Django, DRF, PostgreSQL. Modelos `Activity`, `Participant`, `Enrollment` y `RefreshToken`. Corre con `runserver` en modo desarrollo y con Gunicorn en modo objetivo.
- `frontend/`: Vite + React + TypeScript. Login, listado de actividades, mis inscripciones, inscribirse y cancelar (consume la API v1).

## Inicio rápido (desde un clon limpio)

```bash
git clone https://github.com/Marcos45C/ArqWeb-03-drf.git

```
## Y por la rama hito2Act


| | Modo desarrollo | Modo objetivo |
|---|---|---|
| Frontend | Vite (`pnpm dev`, recarga en caliente) | Build estático servido por Nginx |
| Backend | `runserver` (recarga automática) | Gunicorn |
| Base de datos | PostgreSQL en Docker | PostgreSQL en Docker, volumen propio |
| Punto de entrada | Dos puertos: `:5173` (frontend) y `:8000` (API) | Un solo puerto: `:80` (Nginx) |
| Archivo | `compose.yaml` | `compose.prod.yaml` |

### Modo desarrollo

```bash
docker compose up --build
```
- Aplicación: <http://localhost:5173/>
- API y Swagger: <http://localhost:8000/api/v1/docs>

```bash
docker compose down        # baja los contenedores y conserva los datos
docker compose down -v     # además borra el volumen: arranque 100% limpio
```

### Modo objetivo


```bash
docker compose -f compose.prod.yaml -p aw-prod up --build
```

- Aplicación y API: <http://localhost/> (solo el puerto 80)

`backend` y `db` no publican ningún puerto al host: solo son alcanzables por la red interna de Compose. Se puede comprobar con `docker compose -f compose.prod.yaml -p aw-prod ps`: únicamente `proxy` muestra un mapeo (`0.0.0.0:80->80/tcp`).

El frontend se compila en un servicio aparte (`frontend-build`) que corre `pnpm build`, deja el resultado en un volumen compartido y termina. `proxy` (Nginx) espera a que ese build termine con éxito, sirve el volumen como contenido estático y reenvía `/api/*` al backend.

```bash
docker compose -f compose.prod.yaml -p aw-prod down
```

Archivos propios de este modo: `frontend/Dockerfile.build`, `nginx/nginx.conf` y `compose.prod.yaml`.

### Usuarios de prueba

Los crea el comando `seed_activities` al arrancar

| Email | Contraseña | Participante |
|---|---|---|
| `demo@example.com` | `Demo12345!` | Participante de demostración |
| `other@example.com` | `Demo12345!` | Otra persona |

La contraseña se fija solo al crear la cuenta: reiniciar el stack no la pisa. El comando es idempotente y también restaura las tres actividades de muestra (borra cualquier otra actividad: es un estado de demostración).

### Variables de configuración

Todas tienen un valor por defecto que permite arrancar sin crear un `.env`.

| Variable | Por defecto | Para qué sirve | Compose la pasa |
|---|---|---|---|
| `JWT_SIGNING_KEY` | clave de demostración (48 bytes) | Firma y verifica los access JWT (HS256).  | Sí |
| `ACCESS_SECONDS` | `60` | Duración del access token | Sí |
| `REFRESH_SECONDS` | `604800` (7 días) | Duración del refresh token | No (solo `settings.py`) |
| `REFRESH_COOKIE_SECURE` | `0` | Marca la cookie del refresh como `Secure`. Activar con HTTPS. | No (solo `settings.py`) |
| `POSTGRES_HOST`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_PORT` | `localhost`, `activities`, `activities`, `activities`, `5432` | Conexión a PostgreSQL. Dentro de Compose el host es el nombre del servicio (`db`), que Compose pasa. | Sí |

Para que ocurra antes :

```bash
ACCESS_SECONDS=5 docker compose up -d
```

## Arquitectura


- **Dónde entran las solicitudes:** únicamente por Nginx (`:80`). El navegador no conoce el backend ni la base. En modo desarrollo cumple ese papel el proxy de Vite.
- **Dónde se valida la identidad:** en Django. Cada ruta protegida verifica la firma, el vencimiento y los claims del access JWT y obtiene de ahí al participante. Nginx solo reenvía las cabeceras `Authorization` y `Cookie`.
- **Dónde se guardan los datos:** en PostgreSQL (volumen nombrado): usuarios con su contraseña hasheada, participantes, inscripciones y el **hash** de los refresh tokens. Los access tokens no se guardan en ningún lado.
- **Un solo origen:** frontend y API se sirven desde el mismo origen, por eso no hay CORS y la cookie del refresh viaja sin configuración adicional.

## Autenticación

### Flujo


### Credenciales y dónde viven

| Credencial | Dónde vive | Duración | Qué ocurre al recargar la página |
|---|---|---|---|
| Access (JWT firmado, HS256) | Memoria JavaScript (una variable de `api.ts`). Nunca en `localStorage` ni `sessionStorage`. | 60 s (`ACCESS_SECONDS`) | Se pierde. El frontend lo recupera pidiendo un access nuevo con el refresh. |
| Refresh (valor aleatorio opaco) | Cookie `HttpOnly` `refresh_token`. En la base solo se guarda su hash SHA-256. | 7 días (`REFRESH_SECONDS`), de un solo uso | Permite restaurar la sesión. |

La cookie del refresh lleva `HttpOnly` (JavaScript no puede leerla), `SameSite=Strict` y `Path=/api/v1/auth/` (el navegador solo la envía a las rutas de autenticación, nunca a las de dominio).

El access contiene `sub` (id de usuario), `iat`, `exp`, `iss` y `type: "access"`. No lleva contraseña ni datos del participante. Un JWT firmado **no está cifrado**: cualquiera puede leer su contenido, pero no puede modificarlo sin invalidar la firma.

### Endpoints

| Método y ruta | Credencial | Resultado |
|---|---|---|
| `POST /api/v1/auth/login` | Email y contraseña (JSON) | `200` con `access`, `token_type`, `expires_in` y cookie del refresh. `401 invalid_credentials` si son incorrectas. `400 invalid_request` si el body no es válido. |
| `POST /api/v1/auth/refresh` | Cookie del refresh | `200` con access nuevo y cookie nueva (el refresh anterior queda consumido). `401 invalid_refresh` si falta, venció, ya se usó o la cuenta está inactiva. |
| `POST /api/v1/auth/logout` | Cookie del refresh | `204`. Revoca el refresh y borra la cookie. Idempotente. |
| `GET /api/v1/me` | `Authorization: Bearer <access>` | `200` con el participante actual. `401 authentication_required` sin access válido. |
| Rutas de actividades (v1 y v2) | Públicas | Sin cambios. |
| Rutas `/me/enrollments...` (v1 y v2) | `Authorization: Bearer <access>` | Contrato del Hito 1. `401 authentication_required` sin access válido. |

Las rutas de autenticación se sirven bajo `/api/v1/auth/` y se documentan en el Swagger de v1. Es un cambio compatible (agrega rutas y no modifica las existentes) y v2 reutiliza el mismo mecanismo.

### Cómo se determina quién realiza cada operación

El participante sale **únicamente del access token validado**: la API lee `Authorization: Bearer`, verifica el JWT, obtiene al usuario y de él a su participante. El cliente no puede elegir a quién inscribir: el header `X-Participant-ID` de las actividades anteriores **ya no identifica a nadie** (hay una prueba que lo verifica) y todas las operaciones son de la forma `/me/...`. Por eso un access válido nunca permite ver ni modificar inscripciones ajenas. La cookie del refresh por sí sola tampoco autentica ninguna ruta de dominio.

### Qué pasa con un access ya emitido después del logout

**Sigue siendo válido hasta su vencimiento (como máximo 60 segundos).** El access es un JWT sin estado: el servidor lo acepta si la firma, el emisor y el vencimiento son correctos, sin consultar ninguna tabla, de modo que no hay nada que "revocar". El logout invalida el **refresh** (queda marcado como revocado en la base y la cookie se elimina), por lo que la sesión no se puede renovar: pasado el vencimiento del access, la persona queda efectivamente afuera. La interfaz, además, descarta su copia del access al instante. Hay una prueba automática que demuestra esta ventana.

Ese es el **límite de la solución**: durante hasta `ACCESS_SECONDS` un access copiado antes del logout todavía funciona. Cerrar esa ventana exigiría consultar un estado en cada request (una lista de revocación o la tabla de sesiones), con lo que el access dejaría de ser sin estado. Se eligió una duración corta (60 s) para acotar la ventana sin pagar ese costo.

### Decisiones de diseño

| Decisión | Motivo |
|---|---|
| Access JWT sin estado y refresh opaco guardado como hash | El access se valida sin ir a la base en cada request. El refresh sí necesita estado para poder revocarse, y guardarlo hasheado evita que una filtración de la base entregue credenciales utilizables. |
| Access de 60 s | Acota el daño de un access robado y la ventana posterior al logout. La renovación automática hace que no se note en la interfaz. |
| Access solo en memoria | Reduce la exposición de secretos accesibles a JavaScript. El costo es que se pierde al recargar y hay que renovarlo. |
| Refresh en cookie `HttpOnly`, `Path` acotado y `SameSite=Strict` | JavaScript no puede leerlo, solo viaja a las rutas de autenticación y los otros sitios no pueden hacer que el navegador lo envíe. |
| Sin token CSRF | Con un único origen, `SameSite=Strict` y `Path` acotado, otro sitio no puede provocar que el navegador mande la cookie. Además `refresh` solo devuelve un access que el atacante no puede leer. Se consideró innecesario agregar un token. |
| Refresh rotativo, de un solo uso | Cada renovación consume el refresh y crea otro. Reusar uno consumido da `401`. El consumo es un `UPDATE` condicional dentro de una transacción: solo una petición puede marcarlo como usado, aunque lleguen dos a la vez. |
| Identidad solo desde el token | Cumple que el cliente no elige a quién inscribir y deja las rutas `/me/...` como están. |
| Un solo origen (Nginx / proxy de Vite) | Evita CORS y simplifica el manejo de cookies. |
| HS256 con una clave compartida | Un único servicio emite y verifica los tokens. Un esquema asimétrico tendría sentido con varios verificadores. |
| Errores con la forma `{code, message}` | Se conserva el contrato: `invalid_credentials`, `invalid_refresh` y `authentication_required` se suman a los códigos anteriores. |
| Mismo mensaje para email inexistente y contraseña incorrecta | No revela qué cuentas existen. |
| Usuarios de prueba creados por un seed idempotente | Reproducible desde un clon limpio. La contraseña solo se fija al crear la cuenta. |

### Límites conocidos

- **Access tras el logout:** válido hasta 60 s, como se explicó arriba.
- **Refresh robado:** quien copie la cookie puede usarla hasta que se consuma o venza (7 días). La rotación detecta el reúso, pero no se revoca toda la cadena de refresh al detectarlo.
- **XSS:** `HttpOnly` impide leer el refresh, pero un script malicioso ejecutándose en la página todavía puede usar el access y hacer requests a nombre de la persona. Elegir JWT no elimina el XSS.
- **HTTP local:** la cookie no lleva `Secure` porque el entorno es HTTP. Fuera de la demo hacen falta HTTPS, `REFRESH_COOKIE_SECURE=1`, una `JWT_SIGNING_KEY` privada y `DEBUG` apagado. La clave de demostración está en el repositorio.
- **Dos pestañas renovando a la vez:** como el refresh es de un solo uso, una de las dos puede recibir `401` y volver al login.
- **Sin protección contra fuerza bruta:** el login no limita intentos.
- **Sin limpieza de refresh vencidos:** las filas de `RefreshToken` expiradas no se borran.
- **Alcance:** no hay registro de usuarios, cambio de contraseña ni roles; solo cuentas de prueba y autorización por propiedad (cada persona opera sobre lo suyo).
- **Rotar la clave de firma** invalida todos los access emitidos.


### En el navegador (DevTools)

1. **Application → Cookies:** `refresh_token` figura como `HttpOnly`, con `Path=/api/v1/auth/`. En Local Storage y Session Storage no hay nada.
2. **Network:** al ingresar se ve `login`. Al recargar la página (F5) se ve un `POST /auth/refresh` antes de `/me`. Con `ACCESS_SECONDS=5`, una operación pasada ese tiempo muestra la secuencia: operación → `401` → `refresh` → operación reintentada con `200`.

### Logs de autenticación

Cada intento queda registrado con el `correlation_id` de la interacción, sin contraseñas ni tokens. Eventos: `login_succeeded`, `login_failed`, `token_refreshed`, `refresh_rejected` y `logout` (ver la sección de logs más abajo).

## Ejecución sin Docker (backend o frontend individual)

Para trabajar en un solo lado sin levantar todo el stack, se puede correr `db` en Docker y el resto de forma nativa:

```bash
docker compose up db
```

**Backend (Mac / Linux):**

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
export POSTGRES_HOST=localhost
python manage.py migrate
python manage.py seed_activities
python manage.py runserver
```

**Backend (Windows, PowerShell):**

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
$env:POSTGRES_HOST="localhost"
python manage.py migrate
python manage.py seed_activities
python manage.py runserver
```

Para que el backend nativo alcance la base, el servicio `db` tiene que publicar su puerto en el host: agregá `ports: ["127.0.0.1:5432:5432"]` a `db` en `compose.yaml` (por defecto no lo publica). Si no querés tocarlo, usá el modo desarrollo con Docker.

**Frontend:**

```bash
cd frontend
pnpm install
pnpm dev
```

## API y versionado (v1 / v2)

La API mantiene dos contratos públicos convivientes bajo `/api/v1` y `/api/v2`. Ambas versiones comparten los mismos modelos, reglas de negocio e invariantes; solo cambia la representación de `Activity`. Este contrato HTTP no cambia entre el modo desarrollo y el modo objetivo, ni por la incorporación de la autenticación.

### v1 — representación plana

Es la versión que consume `frontend/`.

- `GET /api/v1/activities`
- `GET /api/v1/activities/{activity_id}`
- `GET /api/v1/me/enrollments`
- `PUT /api/v1/me/enrollments/{activity_id}`
- `DELETE /api/v1/me/enrollments/{activity_id}`

```json
{
  "id": "82ca2d90-7461-4e7c-89fa-bc5498c70e1f",
  "title": "Taller de HTTP",
  "starts_at": "2026-04-10T18:00:00-03:00",
  "capacity": 20,
  "available_slots": 3
}
```

### v2 — disponibilidad agrupada

Mismas rutas y semántica, bajo `/api/v2`. `capacity` y `available_slots` quedan anidados en `availability`; `starts_at` sigue en la raíz. No tiene un consumidor propio en este repositorio: se prueba con Swagger, Postman o `curl`.

- `GET /api/v2/activities`
- `GET /api/v2/activities/{activity_id}`
- `GET /api/v2/me/enrollments`
- `PUT /api/v2/me/enrollments/{activity_id}`
- `DELETE /api/v2/me/enrollments/{activity_id}`

```json
{
  "id": "82ca2d90-7461-4e7c-89fa-bc5498c70e1f",
  "title": "Taller de HTTP",
  "starts_at": "2026-04-10T18:00:00-03:00",
  "availability": {
    "capacity": 20,
    "available_slots": 3
  }
}
```

La inscripción no cambia entre versiones:

```json
{
  "activity_id": "82ca2d90-7461-4e7c-89fa-bc5498c70e1f",
  "enrolled_at": "2026-04-03T15:20:00-03:00"
}
```

### Errores del contrato

Los rechazos propios del contrato usan una forma estable `{"code": "...", "message": "..."}`. El status HTTP clasifica la respuesta y `code` la identifica de manera estable para el cliente.

| Escenario | Status | `code` |
|---|---|---|
| Actividad inexistente | 404 | `activity_not_found` |
| Ruta protegida sin access válido | 401 | `authentication_required` |
| Login con credenciales incorrectas | 401 | `invalid_credentials` |
| Refresh ausente, vencido, ya usado o de cuenta inactiva | 401 | `invalid_refresh` |
| Sin cupo disponible | 409 | `capacity_exhausted` |
| Parámetros o body inválidos | 400 | `invalid_request` |

`PUT` es idempotente (`201` al crear, `200` al repetir conservando `enrolled_at`); `DELETE` es idempotente (`204` siempre que la actividad exista).

### Documentación OpenAPI

Cada versión tiene su propio documento. Las operaciones protegidas declaran el esquema Bearer (botón *Authorize* en Swagger).

- v1: Swagger en <http://localhost:8000/api/v1/docs> y JSON en <http://localhost:8000/api/v1/openapi.json>.
- v2: Swagger en <http://localhost:8000/api/v2/docs> y JSON en <http://localhost:8000/api/v2/openapi.json>.

En modo objetivo, los mismos documentos están en `http://localhost/api/v1/docs` y `http://localhost/api/v2/docs`.

## Correlación de requests (`X-Correlation-ID`)

Todas las operaciones (v1 y v2) aceptan un header opcional `X-Correlation-ID`:

- Si el request lo incluye, la API conserva exactamente ese valor para toda la interacción.
- Si no lo incluye, la API genera un UUID.
- La respuesta siempre devuelve `X-Correlation-ID` con el valor efectivamente usado.

```
PUT /api/v2/me/enrollments/82ca... HTTP/1.1
X-Correlation-ID: demo-42

HTTP/1.1 201 Created
X-Correlation-ID: demo-42
Content-Type: application/json
```

## Logs estructurados

Cada request genera eventos JSON con campos estables (`timestamp`, `level`, `event`, `correlation_id`, `method`, `path`, `result`, y `activity_id` o `participant_id` cuando aplica). Se escriben en consola y en `backend/django_info.log` (no versionado). Nunca incluyen contraseñas, tokens ni cookies.

Eventos emitidos:

- `request_received` / `request_completed`: entrada y salida de cualquier request (middleware `CorrelationIdMiddleware`).
- `enrollment_created`, `enrollment_reused`, `enrollment_rejected`, `enrollment_cancelled`: decisiones de dominio al inscribirse o cancelar.
- `login_succeeded`, `login_failed`, `token_refreshed`, `refresh_rejected`, `logout`: autenticación.

Ejemplo de una interacción completa:

```json
{"timestamp": "2026-08-24T13:40:12-03:00", "level": "info", "event": "request_received", "correlation_id": "demo-42", "method": "PUT", "path": "/api/v2/me/enrollments/82ca...", "result": "received"}
{"timestamp": "2026-08-24T13:40:12-03:00", "level": "info", "event": "enrollment_created", "correlation_id": "demo-42", "method": "PUT", "path": "/api/v2/me/enrollments/82ca...", "result": "created", "activity_id": "82ca...", "participant_id": "a3d8c92e-..."}
{"timestamp": "2026-08-24T13:40:12-03:00", "level": "info", "event": "request_completed", "correlation_id": "demo-42", "method": "PUT", "path": "/api/v2/me/enrollments/82ca...", "result": 201}
```
