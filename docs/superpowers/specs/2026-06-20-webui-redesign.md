# Webui UI Redesign — Spec

## Goal
Restyle all user-facing webui templates to match the Collegium Academicum website (collegiumacademicum.de).

## Design System
- **Colors**: primary teal `#35ADA4`, dark teal `#2f9991`, text `#363636`, bg `#fcfcfc`
- **Font**: Source Sans 3 via Google Fonts
- **CSS framework**: Bulma 0.9.4 via CDN
- **Custom styles**: `broadcast/static/broadcast/ca.css`

## Pages

### base.html
- Navbar: CA logo (img from collegiumacademicum.de/img/logo-small.png) left, username + logout button right. 3px teal bottom border.
- Footer: CA logo, contact email, Impressum / Datenschutz / Kontakt links as teal pill buttons. 3px teal top border.
- 3-step progress indicator (Verfassen → Bestätigen → Ergebnis) shown on broadcast pages via `{% block progress %}`.

### login.html
- Centered card with CA logo above, username/password fields, teal login button.

### compose.html
- Groups as 2-column card grid. Each card: checkbox (left) + group name + channel-count button (right) that expands an inline channel list. Selection click and expand click are independent.
- Private groups shown in a separate section if present.
- Individual channels in a `<details>` collapse at the bottom.

### confirm.html
- Message shown in a styled `<pre>` block.
- Target channels as a bulleted list with teal dots.
- "Senden" (primary) and "Zurück" (outline) buttons.

### result.html
- Success: green check, sent count.
- Partial / failure: warning with error list.
- "Neue Nachricht" link back to compose.

## Out of scope
- Admin UI (stays as-is)
- Mobile responsive beyond Bulma defaults
- i18n infrastructure (labels hardcoded in German)
