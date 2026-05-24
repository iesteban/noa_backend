# ADR-006: Task management — TODOs como extensión del calendario

**Date**: 2026-05-08
**Status**: accepted

## Context

Los contratistas necesitan registrar tareas pendientes que no son citas con hora — "llamar al almacén mañana", "comprar material", "confirmar precio con el proveedor". El modelo actual solo contempla `Appointment` con `starts_at` timestamp, lo que no encaja para tareas de día completo ni para pendientes sin fecha.

El flujo conversacional tiene que resolver dos casos distintos:

- **Tarea con fecha pero sin hora** — "mañana tengo que llamar al almacén" → tiene un día concreto, puede ir al calendario como recordatorio all-day, pero no ocupa un slot horario.
- **Tarea flotante sin fecha** — "tengo que comprar material en algún momento" → no tiene fecha, vive como una lista de pendientes.

## Decision

### Caso 1: Tareas con fecha → extensión de `Appointment`

Añadir un campo `task_mode boolean` a la tabla `appointments`. Cuando es `true`:

- `starts_at` se redondea al día (00:00:00) — representa el día que toca
- `duration_minutes` es null
- En Google Calendar → se crea como evento de día completo (`all_day: true`)
- En respuestas de Noa → se muestra como tarea 📋, no como cita 🔧

Esto reutiliza el `CalendarProvider` existente sin cambios en la abstracción. `GoogleCalendarProvider.create_event()` detecta `task_mode=true` y genera un all-day event.

### Caso 2: Tareas flotantes → nueva tabla `Task`

Las tareas sin fecha son suficientemente distintas como para merecer su propia entidad: no van a Calendar, tienen su propia lista de pendientes, y se marcan como hechas. La tabla es ligera:

```sql
CREATE TABLE tasks (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    contractor_id   UUID NOT NULL REFERENCES contractors(id),
    client_id       UUID REFERENCES clients(id),  -- nullable
    description     TEXT NOT NULL,
    due_date        DATE,                          -- nullable para flotantes
    done_at         TIMESTAMP,
    source          VARCHAR CHECK (source IN ('voice', 'text')),
    created_at      TIMESTAMP NOT NULL DEFAULT now(),
    updated_at      TIMESTAMP NOT NULL DEFAULT now()
);
```

`due_date` permite también tareas "para el viernes" sin hora concreta que el contratista no quiere ver en el calendario.

### Criterio de decisión en el bot

```
¿Tiene hora concreta?
  └─ Sí → Appointment normal (starts_at con hora)
  └─ No → ¿Tiene fecha?
            └─ Sí → ¿El contratista quiere verlo en Calendar?
                      └─ Sí → Appointment con task_mode=true (all-day)
                      └─ No → Task con due_date
            └─ No → Task flotante (due_date null)
```

En práctica, Noa pregunta solo si hay ambigüedad. Por defecto:
- "mañana tengo que llamar al almacén" → propone Appointment all-day (Calendar)
- "tengo que comprar material" → Task flotante directamente

### Nuevas tool definitions

| Tool | Descripción |
|------|-------------|
| `create_task(description, due_date?, client_id?)` | Crea Task flotante o con fecha sin hora |
| `get_pending_tasks(due_date?)` | Lista tareas pendientes, opcionalmente filtradas por fecha |

El `create_appointment` existente absorbe los TODOs all-day vía `task_mode=true`. No se duplica lógica.

### Flujo conversacional

```
Contractor: "Mañana tengo que llamar al almacén a encargar tubería"
Noa: "Anotado ✓
      📋 Llamar al almacén — encargar tubería
      📅 Mañana, 9 de mayo
      ¿Lo añado al calendario como recordatorio del día? (Sí / No)"
```

```
Contractor: "¿Qué tengo mañana?"
Noa: "Mañana, jueves 9 de mayo:
      🔧 10:00 — Cita con Pedro Mejuto (cambio caldera)
      📋 Llamar al almacén — encargar tubería

      Pendientes sin fecha: comprar material"
```

## Consequences

- La abstracción `CalendarProvider` no cambia — solo `create_event()` recibe un flag adicional
- La tabla `Task` es independiente y no afecta la lógica de facturas, trabajos ni citas
- El resumen diario (`¿qué tengo mañana?`) pasa a hacer dos queries: `appointments` para ese día + `tasks` con `due_date` para ese día
- Las tareas flotantes no tienen recordatorio automático — se muestran siempre al final del resumen diario como sección "Pendientes sin fecha"
- Futura extensión posible: recordatorios push para tareas con `due_date` (Phase 2+)
