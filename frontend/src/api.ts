// Cliente HTTP del frontend. Mismo origen: en desarrollo el proxy de Vite reenvía /api
// al backend y en el modo objetivo lo hace Nginx. Por eso todas las rutas son relativas
// y la cookie del refresh viaja sola, sin CORS.

export interface Activity {
  id: string
  title: string
  starts_at: string
  capacity: number
  available_slots: number
}

export interface Enrollment {
  activity_id: string
  enrolled_at: string
}

export interface Me {
  id: string
  name: string
}

/** Error del contrato: status HTTP + code estable + message. */
export class ApiError extends Error {
  status: number
  code: string

  constructor(status: number, code: string, message: string) {
    super(message)
    this.status = status
    this.code = code
  }
}

// El access vive SOLO en esta variable: no hay localStorage ni sessionStorage.
// Recargar la página lo pierde y se recupera con el refresh (cookie HttpOnly).
let accessToken: string | null = null
// Cambia con cada access nuevo: permite saber si otro request ya renovó.
let accessVersion = 0
// Renovación en curso, compartida entre llamadas simultáneas (y el doble efecto de StrictMode).
let refreshPending: Promise<string> | null = null

export function clearAccess(): void {
  accessToken = null
  accessVersion++
}

function setAccess(token: string): void {
  accessToken = token
  accessVersion++
}

async function safeFetch(path: string, init: RequestInit): Promise<Response> {
  try {
    return await fetch(path, { cache: 'no-store', ...init })
  } catch {
    throw new Error('No se pudo contactar la API. Revisá la conexión.')
  }
}

async function toApiError(response: Response): Promise<ApiError> {
  const body = (await response.json().catch(() => ({}))) as { code?: string; message?: string }
  return new ApiError(
    response.status,
    body.code ?? 'http_error',
    body.message ?? `Error HTTP ${response.status}`,
  )
}

/** Rutas públicas: sin credenciales. */
export async function publicRequest<T>(path: string): Promise<T> {
  const response = await safeFetch(path, {})
  if (!response.ok) throw await toApiError(response)
  return (await response.json()) as T
}

/** Valida email y contraseña. El access queda en memoria; el refresh en la cookie HttpOnly. */
export async function login(email: string, password: string): Promise<void> {
  const response = await safeFetch('/api/v1/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })
  if (!response.ok) throw await toApiError(response)
  const data = (await response.json()) as { access: string }
  setAccess(data.access)
}

/** Pide un access nuevo con la cookie del refresh. Como máximo una renovación a la vez. */
export function refreshAccess(): Promise<string> {
  if (!refreshPending) {
    refreshPending = (async () => {
      const response = await safeFetch('/api/v1/auth/refresh', { method: 'POST' })
      if (!response.ok) {
        const error = await toApiError(response)
        // Sin refresh válido no hay sesión: se olvida el access.
        if (error.status === 401) clearAccess()
        throw error
      }
      const data = (await response.json()) as { access: string }
      setAccess(data.access)
      return data.access
    })().finally(() => {
      refreshPending = null
    })
  }
  return refreshPending
}

function sendWithToken(path: string, method: string, token: string): Promise<Response> {
  return safeFetch(path, { method, headers: { Authorization: `Bearer ${token}` } })
}

/**
 * Request autenticado con Bearer. Si vuelve 401 (access vencido) renueva y reintenta
 * UNA sola vez; si el segundo intento también falla, el error llega a la interfaz.
 */
export async function authRequest<T>(path: string, method = 'GET'): Promise<T> {
  const token = accessToken ?? (await refreshAccess())
  const versionUsed = accessVersion

  let response = await sendWithToken(path, method, token)
  if (response.status === 401) {
    // Otro request pudo haber renovado mientras éste esperaba su respuesta.
    const renewed =
      accessToken !== null && accessVersion !== versionUsed ? accessToken : await refreshAccess()
    response = await sendWithToken(path, method, renewed)
  }

  if (!response.ok) throw await toApiError(response)
  return response.status === 204 ? (undefined as T) : ((await response.json()) as T)
}

/** Revoca el refresh en el servidor y olvida el access local, aunque la llamada falle. */
export async function logout(): Promise<void> {
  try {
    const response = await safeFetch('/api/v1/auth/logout', { method: 'POST' })
    if (!response.ok) throw await toApiError(response)
  } finally {
    clearAccess()
  }
}
