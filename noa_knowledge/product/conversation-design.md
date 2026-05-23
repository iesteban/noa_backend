# Conversation Design

## Two user types

Noa serves two distinct personas through the same shared number:

| | Contractor | Client |
|---|---|---|
| **Who** | The autónomo — Noa's paying user | The contractor's customer |
| **Relationship to Noa** | Manages their business through Noa | Interacts with the contractor *via* Noa |
| **Language** | Spanish | Spanish |
| **Access** | Full — all intents | Limited — booking, quotes, payments, history |

---

## Routing

All messages arrive at a single shared Noa number (WhatsApp + Telegram). Routing is a two-step process: **invite token check first, phone number lookup second**.

### Step 1 — invite token check

Before any phone number lookup, the webhook checks whether the message carries a contractor invite token.

| Channel | How the token arrives | Detection |
|---------|----------------------|-----------|
| Telegram | Contractor shares `t.me/noa_bot?start=c_<token>`. Telegram delivers the client's first message as `/start c_<token>`. | `message.text` starts with `/start ` |
| WhatsApp | Contractor shares `https://wa.me/<noa_number>?text=start_<token>`. Client taps the link and sends the pre-filled text. | `message.text` matches `^start_[a-z0-9]+$` |

If a token is found:
```
Token present → look up contractor by invite_token
  ├─ Token valid + X is already a client of that contractor → client mode (skip re-registration)
  ├─ Token valid + X is unknown or client of another contractor → client self-registration flow
  └─ Token invalid or expired → "Este enlace no es válido. Pide al profesional que te mande uno nuevo."
```

### Step 2 — phone number lookup (no token)

```
Inbound message from number X (no invite token)
  ├─ X is a registered contractor → contractor mode
  ├─ X is a known client of exactly one contractor → client mode (that contractor)
  ├─ X is a known client of multiple contractors → ask disambiguation
  │     "¿Con quién quieres contactar?
  │      1. Fontanería García
  │      2. Electricista Ruiz"
  └─ X is unknown → general onboarding prompt
        "Hola, soy Noa. ¿Eres profesional autónomo o quieres contactar con algún profesional?"
```

---

## Confirmation style: act then confirm

The bot acts immediately and shows the result. It then asks for confirmation before committing irreversible actions (sending a PDF, adding to calendar, saving to DB).

```
Contractor: "Estuve 2 horas en casa de Pedro Mejuto cambiando un grifo, 80 euros"
Noa: "Anotado ✓
      Cliente: Pedro Mejuto
      Trabajo: Cambio de grifo
      Duración: 2h · Importe: 80€
      ¿Lo guardo? (Sí / No / Editar)"
```

For irreversible actions (sending an invoice to a client):
```
Noa: "Factura generada. ¿Se la envío a Pedro ahora?"
```

---

## Ambiguity resolution

When a name matches multiple clients, always present a numbered list:

```
Contractor: "Haz la factura para Pedro"
Noa: "¿Cuál Pedro?
      1. Pedro Mejuto
      2. Pedro Sánchez"
```

The contractor replies with the number. Noa resolves and continues without asking again in the same session.

---

## Session memory

- **Within session**: resolved entities (which Pedro) persist for the duration of the conversation
- **Across sessions**: full contractor profile and client history are always available
- **Client recognition**: when a known client messages, Noa greets them by name and knows their history with that contractor

---

## Contractor intents

### Register a client — by message
```
"Añade a Ana García, teléfono 600123456"
Noa: "Cliente nuevo ✓
      Nombre: Ana García
      Teléfono: +34600123456
      ¿Lo guardo? (Sí / No / Editar)"
```
If the name already exists, Noa warns before saving:
```
Noa: "Ya tienes un cliente llamado Ana García (+34600000001).
      ¿Es la misma persona o es otra Ana García?"
```

### Register a client — by contact share
```
Contractor shares a contact card (vCard via Telegram or WhatsApp)
→ Bot parses name and phone from the vCard
→ Shows structured preview → asks to save
Noa: "Cliente nuevo ✓
      Nombre: Pedro Mejuto
      Teléfono: +34612345678
      ¿Lo guardo? (Sí / No / Editar)"
```
If the vCard contains multiple phone numbers, Noa asks which one to use:
```
Noa: "Pedro Mejuto tiene dos teléfonos:
      1. +34612345678 (móvil)
      2. +34912345678 (trabajo)
      ¿Cuál uso para contactarle?"
```

### Log work
```
"Estuve 3 horas en casa de María arreglando la caldera"
→ Extracts: client, duration, work type, amount (if stated)
→ Shows structured note → asks to save
→ Optionally: "¿Genero factura?"
```

### Generate invoice
```
"Haz la factura para Pedro Mejuto por el grifo de hoy"
→ Pulls client data + today's logged work
→ Generates SII-compatible PDF
→ Shows preview → "¿Se la envío a Pedro?"
```

### Generate budget
```
"Presupuesto para María: instalación termo 80L, 350 euros"
→ Generates PDF budget
→ Shows preview → "¿Se lo envío a María?"
```

### Calendar
```
"¿Qué tengo mañana?"
→ Lists tomorrow's appointments

"Cita con Pedro el jueves a las 10"
→ Adds to calendar → confirms
```

### Query history
```
"¿Cuánto le cobré a Pedro el año pasado?"
→ Returns summary from DB

"¿Qué facturas están sin pagar?"
→ Lists unpaid invoices with amounts and dates
```

### Payment follow-up
```
"Recuérdale a Pedro que me debe 80 euros"
→ Sends payment reminder to Pedro via the client bot
→ Confirms to contractor: "Enviado a Pedro Mejuto"
```

### Task inbox
At the start of each contractor session, if there are pending tasks:
```
Noa: "Tienes 3 tareas pendientes. Las más recientes:
      1. Nueva cliente: Ana García (+34600123456) — hace 5 min
      2. Cita solicitada: Ana García — gotera en baño — jueves — hace 5 min
      3. Nueva cliente: Marta Ruiz (+34611223344) — hace 2h
      ¿Qué hago con alguna?"
```
The contractor can resolve tasks inline:
```
Contractor: "Acepta a Ana García"
Noa:        "Ana García añadida como cliente ✓
             Tiene también una cita pendiente el jueves. ¿La confirmo?"
Contractor: "Sí"
Noa:        "Cita confirmada. Le aviso a Ana."
→ Client receives: "Tu cita con Fontanería García el jueves está confirmada."
```
Rejecting a client:
```
Contractor: "Rechaza a Marta Ruiz"
Noa:        "¿Quieres que le avise o lo dejo sin respuesta?"
Contractor: "Avísale"
Noa:        "Hecho. Le he dicho que de momento no tienes disponibilidad."
```

---

## Client intents

Clients interact with the contractor's "face" — Noa responds on behalf of the contractor using their configured info and calendar.

### Self-registration via invite link
The contractor shares a personal invite link (e.g. `t.me/noa_bot?start=c_abc123`). When the client taps it:
```
Noa:    "Hola, has contactado con Fontanería García a través de Noa.
         ¿Cómo te llamas?"
Client: "Ana García"
Noa:    "Perfecto, Ana. Ya puedes:
         · Pedir una cita
         · Pedir un presupuesto
         Pedro te confirmará en breve."
→ Contractor gets task: "Nueva cliente: Ana García (+34600123456)"
```
If the Telegram profile name is already available, Noa proposes it:
```
Noa:    "Hola, has contactado con Fontanería García.
         Tu nombre en Telegram es 'Ana G.' — ¿es correcto o prefieres otro?"
Client: "Ana García está bien"
```

### Book an appointment (pending contractor approval)
Available immediately after self-registration, before contractor accepts:
```
Client: "Quiero pedir una cita"
Noa:   "¿Para qué tipo de trabajo y cuándo te viene bien?"
Client: "Tengo una gotera en el baño. El jueves si puede ser."
Noa:   "Apuntado. Te confirmamos en cuanto Pedro lo acepte."
→ Contractor gets task: "Cita solicitada: Ana García — gotera en baño — jueves"
```
Once contractor confirms:
```
→ Client receives: "Tu cita con Fontanería García el jueves está confirmada."
```

### Request a quote
```
Client: "¿Cuánto me costaría cambiar el termo?"
Noa:   "Depende del modelo y la instalación. Mándame una foto
        y te doy una estimación."
Client: [sends photo]
Noa:   "Para un termo de tamaño similar la instalación suele estar
        entre 180€ y 250€ + el equipo. ¿Quieres que te prepare
        un presupuesto formal?"
→ If yes: notifies contractor to confirm or auto-generates budget
```

### Book an appointment (active client)
```
Client: "Hola, tengo una gotera en el baño"
Noa:   "Hola Ana. Te paso con Fontanería García.
        ¿Cuándo te viene bien?
        Tengo disponibilidad el jueves 3 a las 10h o el viernes 4 a las 16h."
Client: "El jueves"
Noa:   "Perfecto, apuntado para el jueves 3 de mayo a las 10h.
        Te confirmo la dirección: [calle]. ¿Es correcto?"
→ Adds to contractor's calendar
→ Pings contractor: "Nueva cita: Ana Gómez, jueves 3/5 10h — gotera en baño"
```

### Pay an invoice
```
Client: "Me ha llegado una factura de 120€, ¿cómo pago?"
Noa:   "Puedes pagar por Bizum al [número] o por transferencia
        al [IBAN]. Indica el concepto: Factura [número]."
```

### View invoice history
```
Client: "¿Puedo ver mis facturas?"
Noa:   "Tus últimas facturas con Fontanería García:
        · Factura 2025-034 — 80€ — Pagada
        · Factura 2025-021 — 120€ — Pendiente"
```

---

## Calls (Phase 3+)

When a client calls the Noa VoIP number:

```
[Call received]
Bot: "Hola, has llamado a Fontanería García. Ahora mismo no
     puede atenderte. Soy Noa, su asistente. ¿En qué puedo ayudarte?"

→ Can schedule an appointment by voice
→ Can take a message
→ Escalation: if client says "es urgente" or bot cannot resolve →
     real-time ping to contractor in their Noa chat:
     "Llamada entrante de Ana Gómez — dice que es urgente.
      ¿Cojo la llamada o le digo que te llama en 10 minutos?"
```

---

## Escalation (client → contractor)

When a client asks something Noa cannot handle:

1. Bot tells client: "Voy a avisar a [Contractor] para que te responda."
2. Bot pings contractor in their own Noa chat:
   ```
   "Ana Gómez te pregunta: '¿La reparación de la semana pasada
    tiene garantía?' ¿Qué le respondo?"
   ```
3. Contractor replies to Noa → Noa forwards to client
4. Client never knows they're talking to a bot unless the contractor wants them to
