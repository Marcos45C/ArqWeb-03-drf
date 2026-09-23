# Ejemplo 03: DRF
 
Aplicación Django con una API de actividades e inscripciones consumida desde React. El contrato ejecutable y la documentación OpenAPI se generan con Django REST Framework y drf-spectacular. La API expone dos versiones convivientes (`v1` y `v2`), soporta correlación de requests vía `X-Correlation-ID` y emite logs estructurados en JSON.
 
El repositorio contiene dos aplicaciones independientes:
 
- `backend/`: Django, PostgreSQL, los modelos `Activity`, `Participant` y `Enrollment`, y la API HTTP (v1 y v2). Corre con `runserver` en modo desarrollo y con Gunicorn en modo objetivo.
- `frontend/`: Vite + React + TypeScript consumiendo la colección de actividades (versión v1 de la API).
## Modos de ejecución
 
El repositorio ofrece dos formas distintas de correr el mismo sistema, cada una pensada para una necesidad diferente. No comparten el mismo archivo de Compose porque su topología interna es distinta (procesos de desarrollo con recarga en caliente vs. build estático servido por un reverse proxy).
 
| | Modo desarrollo | Modo objetivo |
|---|---|---|
| Frontend | Vite (`pnpm dev`, recarga en caliente) | Build estático servido por Nginx |
| Backend | `runserver` (recarga automática) | Servidor de aplicación (Gunicorn) |
| Base de datos | PostgreSQL vía Docker, reproducible | PostgreSQL vía Docker, reproducible |
| Punto de entrada | Dos puertos: `:8000` (API) y `:5173` (frontend) | Un solo puerto: `:80` (Nginx), que reenvía `/api/*` al backend |
| Archivo | `compose.yaml` | `compose.prod.yaml` |
 
### Modo desarrollo
 
Pensado para programar día a día: hot reload en ambos lados, PostgreSQL reproducible sin instalar nada localmente.
 
```bash
docker compose up --build
```
 
- Frontend (Vite): <http://127.0.0.1:5173/>
- Backend (API): <http://127.0.0.1:8000/>
Los bind mounts (`./backend:/app`, `./frontend:/app`) hacen que los cambios en el código se reflejen sin reconstruir la imagen. Solo hace falta `--build` la primera vez, o después de cambiar `requirements.txt`/`package.json`.
 
Para bajar el stack conservando los datos:
 
```bash
docker compose down
```
 
Para bajarlo destruyendo también la base (arranque 100% limpio):
 
```bash
docker compose down -v
```
 
### Modo objetivo
 
Pensado para parecerse a una ejecución productiva local: build de React, servidor de aplicación para Django, Nginx como único punto de entrada público. Usa un archivo de Compose separado (`-f`) y un nombre de proyecto propio (`-p`) para no pisar al modo desarrollo si ambos se levantan en algún momento en la misma máquina.
 
```bash
docker compose -f compose.prod.yaml -p aw-prod up --build
```
 
- Único punto de entrada: <http://127.0.0.1/>
- API a través del proxy: <http://127.0.0.1/api/v1/activities>
Backend y PostgreSQL no publican ningún puerto al host — solo son alcanzables por la red interna de Compose. Se puede confirmar con:
 
```bash
docker compose -f compose.prod.yaml -p aw-prod ps
```
 
`backend` y `db` muestran su puerto interno (`8000/tcp`, `5432/tcp`) sin ningún `0.0.0.0:→` adelante; solo `proxy` tiene un mapeo real hacia el host (`0.0.0.0:80->80/tcp`).
 
El frontend se compila en un servicio aparte (`frontend-build`) que corre `pnpm build` una vez, deja el resultado en un volumen compartido y termina; `proxy` (Nginx, sin build propio) espera a que ese build termine con éxito y sirve ese volumen como contenido estático, reenviando `/api/*` al backend.
 
Para bajar el stack:
 
```bash
docker compose -f compose.prod.yaml -p aw-prod down
```
 
Archivos propios de este modo:
 
- `frontend/Dockerfile.build` — imagen efímera que solo compila el frontend.
- `nginx/nginx.conf` — configuración del reverse proxy (`/` sirve el build, `/api/*` reenvía al backend).
- `compose.prod.yaml` — orquesta `db` + `backend` (Gunicorn) + `frontend-build` + `proxy`.
## Puesta en marcha sin Docker (backend o frontend individual)
 
Para trabajar en un solo lado sin levantar todo el stack, se puede correr `db` en Docker y el resto nativo:
 
```bash
docker compose up db
```
 
**Backend (Mac / Linux):**
 
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
POSTGRES_HOST=localhost python manage.py migrate
POSTGRES_HOST=localhost python manage.py seed_activities
POSTGRES_HOST=localhost python manage.py runserver
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
 
> Si PowerShell bloquea la activación del entorno virtual, corré una vez `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.
 
**Frontend:**
 
```bash
cd frontend
pnpm install
pnpm dev
```
 
## Verificación rápida
 
```bash
cd backend
python manage.py test
 
cd ../frontend
pnpm build
```
 
## API y versionado (v1 / v2)
 
La API mantiene dos contratos públicos convivientes bajo `/api/v1` y `/api/v2`. Ambas versiones comparten los mismos modelos, reglas de negocio e invariantes; solo cambia la representación de `Activity`. Este contrato HTTP no cambia entre el modo desarrollo y el modo objetivo — es justo lo que exige la Actividad 06.
 
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
 
