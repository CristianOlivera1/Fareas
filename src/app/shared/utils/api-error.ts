export function extractDetail(err: unknown): string {
  const anyErr = err as { error?: { detail?: string }; message?: string };
  return anyErr?.error?.detail ?? anyErr?.message ?? 'Error de conexión con el servidor';
}
