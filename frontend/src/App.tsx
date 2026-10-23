import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import './App.css'
import './hito2.css'
import {
  ApiError,
  authRequest,
  clearAccess,
  login,
  logout,
  publicRequest,
  refreshAccess,
} from './api'
import type { Activity, Enrollment, Me } from './api'

interface Snapshot {
  activities: Activity[]
  me: Me | null
  enrollments: Enrollment[]
}

/** Trae el catálogo (público) y, con sesión, el perfil y las inscripciones propias. */
async function fetchSnapshot(signedIn: boolean): Promise<Snapshot> {
  const [activities, privateData] = await Promise.all([
    publicRequest<Activity[]>('/api/v1/activities'),
    signedIn
      ? Promise.all([
          authRequest<Me>('/api/v1/me'),
          authRequest<Enrollment[]>('/api/v1/me/enrollments'),
        ])
      : Promise.resolve(null),
  ])
  return { activities, me: privateData?.[0] ?? null, enrollments: privateData?.[1] ?? [] }
}

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : 'Error desconocido'
}

function App() {
  const [activities, setActivities] = useState<Activity[]>([])
  const [me, setMe] = useState<Me | null>(null)
  const [enrollments, setEnrollments] = useState<Enrollment[]>([])
  const [restoring, setRestoring] = useState(true)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')

  function apply(data: Snapshot) {
    setActivities(data.activities)
    setMe(data.me)
    setEnrollments(data.enrollments)
  }

  /** Olvida la sesión en el cliente: access en memoria y datos privados. */
  function forgetSession() {
    clearAccess()
    setMe(null)
    setEnrollments([])
    setPassword('')
  }

  // Al abrir o recargar la página la memoria está vacía: se intenta recuperar la sesión
  // con el refresh de la cookie. Sin refresh válido (401) simplemente se muestra el login.
  useEffect(() => {
    let active = true

    async function restore() {
      let signedIn = false
      try {
        await refreshAccess()
        signedIn = true
      } catch (error) {
        if (active && !(error instanceof ApiError && error.status === 401)) {
          setNotice(messageOf(error))
        }
      }
      try {
        const data = await fetchSnapshot(signedIn)
        if (active) apply(data)
      } catch (error) {
        if (active) {
          clearAccess()
          setNotice(messageOf(error))
        }
      } finally {
        if (active) setRestoring(false)
      }
    }

    void restore()
    return () => {
      active = false
    }
  }, [])

  async function signIn(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setBusy(true)
    setNotice('')
    try {
      await login(email.trim(), password)
      setPassword('')
      apply(await fetchSnapshot(true))
    } catch (error) {
      clearAccess()
      setNotice(messageOf(error))
    } finally {
      setBusy(false)
    }
  }

  async function signOut() {
    setBusy(true)
    setNotice('')
    try {
      await logout()
      setNotice('Saliste de la aplicación.')
    } catch {
      setNotice('Se limpió esta pantalla, pero no se pudo confirmar la revocación en el servidor.')
    } finally {
      forgetSession()
      setBusy(false)
    }
  }

  async function changeEnrollment(activityId: string, method: 'PUT' | 'DELETE') {
    setBusy(true)
    setNotice('')
    try {
      await authRequest<unknown>(`/api/v1/me/enrollments/${activityId}`, method)
      apply(await fetchSnapshot(true))
      setNotice(method === 'PUT' ? 'Inscripción realizada.' : 'Inscripción cancelada.')
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        forgetSession()
        setNotice('Tu sesión venció o no es válida. Ingresá nuevamente.')
      } else {
        // 404 (la actividad ya no existe) o 409 (sin cupo): se muestra el mensaje del contrato
        // y se refresca el catálogo para que los cupos no queden desactualizados.
        setNotice(messageOf(error))
        publicRequest<Activity[]>('/api/v1/activities').then(setActivities).catch(() => {})
      }
    } finally {
      setBusy(false)
    }
  }

  const enrolledIds = new Set(enrollments.map((enrollment) => enrollment.activity_id))
  const titleOf = (activityId: string) =>
    activities.find((activity) => activity.id === activityId)?.title ?? activityId

  return (
    <main>
      <h1>Actividades e inscripciones</h1>

      {notice && (
        <p role="status" className="notice">
          {notice}
        </p>
      )}

      {restoring ? (
        <p>Comprobando sesión…</p>
      ) : me === null ? (
        <form className="login-form" onSubmit={(event) => void signIn(event)}>
          <h2>Ingresar</h2>
          <label>
            Email
            <input
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              autoComplete="username"
              required
              disabled={busy}
            />
          </label>
          <label>
            Contraseña
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="current-password"
              required
              disabled={busy}
            />
          </label>
          <button type="submit" disabled={busy}>
            {busy ? 'Procesando…' : 'Ingresar'}
          </button>
        </form>
      ) : (
        <>
          <div className="session-bar">
            <p>
              Sesión de <strong>{me.name}</strong>
            </p>
            <button type="button" onClick={() => void signOut()} disabled={busy}>
              Salir
            </button>
          </div>

          <h2>Mis inscripciones</h2>
          {enrollments.length === 0 ? (
            <p>No tenés inscripciones todavía.</p>
          ) : (
            <ul>
              {enrollments.map((enrollment) => (
                <li key={enrollment.activity_id}>
                  {titleOf(enrollment.activity_id)} —{' '}
                  <time dateTime={enrollment.enrolled_at}>{enrollment.enrolled_at}</time>{' '}
                  <button
                    type="button"
                    onClick={() => void changeEnrollment(enrollment.activity_id, 'DELETE')}
                    disabled={busy}
                  >
                    Cancelar
                  </button>
                </li>
              ))}
            </ul>
          )}
        </>
      )}

      <h2>Actividades</h2>
      {activities.length === 0 && !restoring ? (
        <p>No hay actividades cargadas.</p>
      ) : (
        <div className="table-container">
          <table>
            <thead>
              <tr>
                <th scope="col">Título</th>
                <th scope="col">Comienza</th>
                <th scope="col">Capacidad</th>
                <th scope="col">Cupos disponibles</th>
                {me && <th scope="col">Acción</th>}
              </tr>
            </thead>
            <tbody>
              {activities.map((activity) => {
                const enrolled = enrolledIds.has(activity.id)
                return (
                  <tr key={activity.id}>
                    <td>{activity.title}</td>
                    <td>
                      <time dateTime={activity.starts_at}>
                        {new Date(activity.starts_at).toISOString()}
                      </time>
                    </td>
                    <td>{activity.capacity}</td>
                    <td>{activity.available_slots}</td>
                    {me && (
                      <td>
                        {enrolled ? (
                          'Ya estás inscripto/a'
                        ) : (
                          <button
                            type="button"
                            onClick={() => void changeEnrollment(activity.id, 'PUT')}
                            disabled={busy}
                          >
                            Inscribirme
                          </button>
                        )}
                      </td>
                    )}
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      <p className="hint">
        El access token vive solo en memoria y se renueva con una cookie HttpOnly. Observá las
        peticiones en la pestaña Network.
      </p>
    </main>
  )
}

export default App
