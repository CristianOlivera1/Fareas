/** Mensaje de error legible a partir de la respuesta del backend.
 *
 * FastAPI devuelve `{"detail": "..."}` tanto en los DomainError (409/404/422)
 * como en los errores de validación, así que esta es la fuente principal.
 */
export function extractDetail(err: unknown): string {
  const anyErr = err as { error?: { detail?: string }; message?: string };
  return anyErr?.error?.detail ?? anyErr?.message ?? 'Error de conexión con el servidor';
}
