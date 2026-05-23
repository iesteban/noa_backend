# Noa — Guía de marca

> Paleta sincronizada con `botnoa.com` (mayo 2026)

## Archivos

| Archivo | Uso |
|---|---|
| `noa-icon.svg` | Avatar de WhatsApp/Telegram, favicon, app icon |
| `noa-lockup-light.svg` | Logotipo sobre fondos claros (blanco, `#f9fafb`, `#eff6ff`) |
| `noa-lockup-dark.svg` | Logotipo sobre fondos oscuros o brand blue |
| `noa-wordmark.svg` | Solo el nombre, sin ícono |

---

## Logotipo

El logotipo de Noa combina un ícono de burbuja de conversación con el wordmark en cursiva. El ícono lleva el peso del color de marca; el wordmark es limpio y unitario.

**Reglas:**
- No separar el ícono del wordmark salvo en contextos de ícono puro (avatar, favicon)
- No añadir taglines, divisores ni elementos decorativos al lockup
- No recolorear el ícono — siempre brand blue sobre blanco
- El wordmark va siempre en cursiva Fraunces Light, sin acento de color propio

---

## Ícono

Burbuja de conversación con tres puntos de opacidad decreciente (indicador de escritura AI). Contenido en un rounded square con radio 14px.

- Fondo: `#2563eb` (Brand blue)
- Burbuja: `#ffffff`
- Puntos: `#2563eb` a opacidades 100%, 50%, 20%

Para avatar de WhatsApp/Telegram usar `noa-icon.svg` exportado a PNG 512×512px.

---

## Tipografía

**Wordmark:** Fraunces — Light (300) — Italic
Google Fonts: `https://fonts.google.com/specimen/Fraunces`

**Interfaz / textos UI:** -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif
(misma font stack que la landing)

---

## Paleta de color

Extraída directamente de `botnoa.com`:

| Variable CSS | Hex | Uso |
|---|---|---|
| `--brand` | `#2563eb` | Color de marca principal, ícono, CTAs, links |
| `--brand-d` | `#1d4ed8` | Hover de brand, estados activos |
| `--brand-subtle` | `#dbeafe` | Badges, highlights suaves |
| `--brand-bg` | `#eff6ff` | Fondo hero, fondos de secciones con tinte blue |
| `--text` | `#111827` | Texto principal |
| `--muted` | `#6b7280` | Texto secundario, subtítulos |
| `--bg` | `#f9fafb` | Fondo de secciones alternas |
| `--white` | `#ffffff` | Fondo principal, tarjetas |
| `--border` | `#e5e7eb` | Bordes, separadores |

### Variables CSS

```css
:root {
  --noa-brand:        #2563eb;
  --noa-brand-dark:   #1d4ed8;
  --noa-brand-subtle: #dbeafe;
  --noa-brand-bg:     #eff6ff;
  --noa-text:         #111827;
  --noa-muted:        #6b7280;
  --noa-bg:           #f9fafb;
  --noa-white:        #ffffff;
  --noa-border:       #e5e7eb;
  --noa-radius:       12px;
}
```

---

## Uso del color

- **Sobre blanco / `#f9fafb` / `#eff6ff`:** wordmark en `#111827`
- **Sobre `#2563eb` o fondos oscuros:** wordmark en `#ffffff`, ícono con fondo `rgba(0,0,0,0.2)`
- **Sombra del CTA principal:** `box-shadow: 0 4px 14px rgba(37,99,235,0.3)`

---

## Contextos específicos

### Avatar de WhatsApp / Telegram
Usar `noa-icon.svg`. Exportar a PNG 512×512px con fondo `#2563eb`.

### Cabecera web / landing
Usar `noa-lockup-light.svg` sobre fondo blanco o `#eff6ff`.

### CTA banner (fondo brand blue)
Usar `noa-lockup-dark.svg` sobre `#2563eb`.

### Facturas y PDFs generados
Usar `noa-wordmark.svg` en pie de página, color `#111827` o `#ffffff` según fondo.

---

## Lo que no hacer

- No estirar ni deformar el ícono
- No usar el wordmark en romano (solo cursiva)
- No añadir sombras, brillos ni efectos al logotipo
- No usar colores fuera de la paleta para el logotipo
- No mostrar el texto "No" con énfasis visual separado del resto del nombre
- No cambiar el radio del rounded square del ícono (14px sobre base 52×52)
