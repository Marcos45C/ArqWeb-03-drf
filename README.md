# Ejemplo 03: DRF

Aplicación Django con una API de actividades e inscripciones consumida desde React. El contrato ejecutable y la documentación OpenAPI se generan con Django REST Framework y drf-spectacular.

El repositorio comienza con dos aplicaciones independientes:

- `backend/`: Django, SQLite, los modelos `Activity`, `Participant` y `Enrollment`, y la API HTTP.
- `frontend/`: Vite + React + TypeScript consumiendo la colección de actividades.

## Puesta en marcha local

### 1. Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate // .\.venv\Scripts\Activate
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py seed_activities
python manage.py runserver
```

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

## API y OpenAPI

La API implementa:

- `GET /api/v1/activities`
- `GET /api/v1/activities/{activity_id}`
- `GET /api/v1/me/enrollments`
- `PUT /api/v1/me/enrollments/{activity_id}`
- `DELETE /api/v1/me/enrollments/{activity_id}`

Las rutas bajo `/me` reciben el UUID de la identidad controlada en el header `X-Participant-ID`. `seed_activities` crea el participante de demostración `a3d8c92e-4f1a-4e5b-8c7d-9e0f1a2b3c4d`.

Con el backend iniciado, la interfaz Swagger UI está en <http://127.0.0.1:8000/api/v1/docs> y el documento OpenAPI JSON en <http://127.0.0.1:8000/api/v1/openapi.json>. Allí se describen parámetros, representaciones y respuestas `200`, `201`, `204`, `400`, `404`, `405` y `409` según cada operación.

## Persistencia de las inscripciones

Al inscribir, se agrega una fila a `activities_enrollment` que referencia al participante y a la actividad. Al cancelar, se elimina esa fila. La tabla `activities_activity` no cambia: `available_slots` se calcula restando a `capacity` la cantidad de inscripciones persistidas.

La restricción única sobre `(participant, activity)` evita inscripciones duplicadas. `PUT` es idempotente: crea con `201` la primera vez y devuelve la inscripción existente con `200` al repetirlo. `DELETE` responde `204` aunque la inscripción ya no exista.
