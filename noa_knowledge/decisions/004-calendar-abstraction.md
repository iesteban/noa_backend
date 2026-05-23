# ADR-004: Calendar integration — Google Calendar with provider abstraction

**Date**: 2026-04-27
**Status**: accepted

## Decision

Integrate Google Calendar for Phase 1. Build behind a `CalendarProvider` abstraction so Apple Calendar (and others) can be added without changing business logic.

## Interface

```python
class CalendarProvider(Protocol):
    def create_event(self, appointment: Appointment) -> str:
        """Returns the external event ID."""

    def update_event(self, external_id: str, appointment: Appointment) -> None: ...

    def delete_event(self, external_id: str) -> None: ...

    def list_events(self, contractor_id: UUID, start: datetime, end: datetime) -> list[CalendarEvent]: ...

    def check_availability(self, contractor_id: UUID, start: datetime, end: datetime) -> bool: ...
```

Concrete implementations: `GoogleCalendarProvider` (Phase 1), `AppleCalendarProvider` (future).

## Data model impact

`appointments` table stores:
- `calendar_provider` enum: `google`, `apple` (default `google`)
- `external_calendar_id` varchar: the event ID returned by the provider

## Google Calendar specifics

- OAuth2 per contractor — each contractor connects their Google account
- Scopes: `https://www.googleapis.com/auth/calendar`
- Store tokens in a `calendar_tokens` table: `(contractor_id, provider, access_token, refresh_token, expires_at)`
- Refresh tokens automatically before expiry

## Consequences

- Adding Apple Calendar later requires one new class implementing `CalendarProvider`, no changes to business logic
- Each contractor must OAuth-connect their calendar during onboarding
- Contractors without Google Calendar cannot use scheduling features until Apple is supported
