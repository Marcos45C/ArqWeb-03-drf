# Ejemplo 03: DRF

Aplicación Django con una API de actividades e inscripciones consumida desde React. El contrato ejecutable y la documentación OpenAPI se generan con Django REST Framework y drf-spectacular. La API expone dos versiones convivientes (`v1` y `v2`), soporta correlación de requests vía `X-Correlation-ID` y emite logs estructurados en JSON.

El repositorio contiene dos aplicaciones independientes:

- `backend/`: Django, SQLite, los modelos `Activity`, `Participant` y `Enrollment`, y la API HTTP (v1 y v2).
- `frontend/`: Vite + React + TypeScript consumiendo la colección de actividades (versión v1 de la API).

## Puesta en marcha local

### 1. Backend

**Mac / Linux:**

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py seed_activities
python manage.py runserver
```

**Windows (PowerShell):**

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py seed_activities
python manage.py runserver
```

> Si PowerShell bloquea la activación del entorno virtual con un error de ejecución de scripts, corré una vez `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` y volvé a intentar.

Abrir <http://127.0.0.1:8000/>.

### 2. Frontend

En otra terminal:

```bash
cd frontend
pnpm install
pnpm dev
```

Abrir <http://127.0.0.1:5173/>.

## Puesta en marcha con Docker Compose

Docker Compose queda preparado para uso futuro; no es necesario para seguir la primera clase.

```bash
docker compose up --build
```

El backend queda disponible en <http://127.0.0.1:8000/> y el frontend en <http://127.0.0.1:5173/>. El comando del backend aplica las migraciones y carga los datos de muestra antes de iniciar el servidor.

Para detener ambos servicios:

```bash
docker compose down
```

## Verificación rápida

```bash
cd backend
python manage.py test

cd ../frontend
pnpm build
```

## API y versionado (v1 / v2)

La API mantiene dos contratos públicos convivientes bajo `/api/v1` y `/api/v2`. Ambas versiones comparten los mismos modelos, reglas de negocio e invariantes; solo cambia la representación de `Activity`.

### v1 — representación plana

Esta es la versión que consume actualmente `frontend/`.

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

Mismas rutas y semántica, bajo `/api/v2`. `capacity` y `available_slots` quedan anidados en `availability`; `starts_at` sigue en la raíz. Todavía no tiene un consumidor propio en este repositorio — se prueba directamente vía Swagger, Postman, o `curl`/PowerShell.

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

Enrollment no cambia entre versiones:

```json
{
  "activity_id": "82ca2d90-7461-4e7c-89fa-bc5498c70e1f",
  "enrolled_at": "2026-04-03T15:20:00-03:00"
}
```

### Identidad y errores

Las rutas bajo `/me` reciben el UUID de la identidad controlada en el header `X-Participant-ID`. `seed_activities` crea el participante de demostración `a3d8c92e-4f1a-4e5b-8c7d-9e0f1a2b3c4d`.

Los rechazos propios del contrato usan una forma estable `{"code": "...", "message": "..."}`:

| Escenario | Status | `code` |
|---|---|---|
| Actividad inexistente | 404 | `activity_not_found` |
| Sin identidad válida en ruta protegida | 401 | `authentication_required` |
| Sin cupo disponible | 409 | `capacity_exhausted` |
| Parámetros de request inválidos | 400 | `invalid_request` |

`PUT` es idempotente (201 al crear, 200 al repetir conservando `enrolled_at`); `DELETE` es idempotente (204 siempre que la actividad exista).

### Documentación OpenAPI

Con el backend iniciado, cada versión tiene su propia documentación:

- v1: Swagger en <http://127.0.0.1:8000/api/v1/docs>, JSON en <http://127.0.0.1:8000/api/v1/openapi.json>.
- v2: Swagger en <http://127.0.0.1:8000/api/v2/docs>, JSON en <http://127.0.0.1:8000/api/v2/openapi.json>.

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

Cada request genera eventos JSON con campos estables (`timestamp`, `level`, `event`, `correlation_id`, `method`, `path`, `result`, y `activity_id`/`participant_id` cuando aplica). Se escriben en consola y en el archivo `backend/django_info.log` (no versionado, ver `.gitignore`).

Eventos emitidos:

- `request_received` / `request_completed` — entrada y salida de cualquier request (middleware `CorrelationIdMiddleware`).
- `enrollment_created`, `enrollment_reused`, `enrollment_rejected`, `enrollment_cancelled` — decisiones de dominio al inscribirse o cancelar.

Ejemplo de una interacción completa:

```json
{"timestamp": "2026-08-24T13:40:12-03:00", "level": "info", "event": "request_received", "correlation_id": "demo-42", "method": "PUT", "path": "/api/v2/me/enrollments/82ca...", "result": "received"}
{"timestamp": "2026-08-24T13:40:12-03:00", "level": "info", "event": "enrollment_created", "correlation_id": "demo-42", "method": "PUT", "path": "/api/v2/me/enrollments/82ca...", "result": "created", "activity_id": "82ca...", "participant_id": "a3d8c92e-..."}
{"timestamp": "2026-08-24T13:40:12-03:00", "level": "info", "event": "request_completed", "correlation_id": "demo-42", "method": "PUT", "path": "/api/v2/me/enrollments/82ca...", "result": 201}
```

### Buscar los eventos de una interacción por `correlation_id`

**Mac / Linux:**

```bash
grep "demo-42" backend/django_info.log
```

**Windows (PowerShell):**

```powershell
Select-String -Path backend\django_info.log -Pattern "demo-42"
```

## Persistencia de las inscripciones

Al inscribir, se agrega una fila a `activities_enrollment` que referencia al participante y a la actividad. Al cancelar, se elimina esa fila. La tabla `activities_activity` no cambia: `available_slots` se calcula restando a `capacity` la cantidad de inscripciones persistidas.

La restricción única sobre `(participant, activity)` evita inscripciones duplicadas.