# Kozmik Lahmacun frontend

SvelteKit product UI for the Java control plane. The browser only uses relative
`/api/*` Java endpoints. It never connects directly to Python, Kafka, Keycloak
Admin, an LLM provider, or infrastructure services.

## Local development

Start the Java backend and local infrastructure from the repository root, then:

```bash
cd frontend
npm install
npm run dev
```

The app authenticates through Java at `/oauth2/authorization/keycloak` and
resolves the session through `/api/auth/me`.

## Verification

```bash
npm run check
npm test
npm run build
npx playwright install chromium
npm run test:e2e
```

Playwright tests mock only Java browser-facing APIs. The production UI does not
ship mock data. Turkish is the default locale; English and light/dark themes are
available from the authenticated shell.
