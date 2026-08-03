import { expect, test, type Page } from '@playwright/test';

const user = {
  userId: 'user-1',
  username: 'ada',
  displayName: 'Ada Yönetici',
  email: 'ada@example.test',
  roles: ['ADMIN']
};

async function authenticate(page: Page) {
  await page.route('**/api/auth/me', (route) => route.fulfill({ json: user }));
  await page.route('**/api/auth/csrf', (route) =>
    route.fulfill({ json: { headerName: 'X-XSRF-TOKEN', parameterName: '_csrf', token: 'test-csrf' } })
  );
  await page.route('**/api/executions', (route) =>
    route.fulfill({ json: { schemaVersion: '1.0', executions: [] } })
  );
  await page.route('**/api/health/services', (route) =>
    route.fulfill({
      json: {
        checkedAt: new Date().toISOString(),
        services: [
          { service: 'backend', status: 'AVAILABLE' },
          { service: 'executor', status: 'AVAILABLE' },
          { service: 'llm', status: 'AVAILABLE' }
        ]
      }
    })
  );
}

test('custom login posts credentials only to the Java backend and creates the browser session', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('kozmik-locale', 'en'));
  let authenticated = false;
  let submitted: Record<string, string> | undefined;
  await page.route('**/api/auth/csrf', (route) =>
    route.fulfill({ json: { headerName: 'X-XSRF-TOKEN', parameterName: '_csrf', token: 'test-csrf' } })
  );
  await page.route('**/api/auth/me', (route) =>
    authenticated ? route.fulfill({ json: user }) : route.fulfill({ status: 401 })
  );
  await page.route('**/api/auth/login', async (route) => {
    submitted = route.request().postDataJSON();
    authenticated = true;
    await route.fulfill({ status: 204 });
  });
  await page.route('**/api/chat/threads', (route) =>
    route.fulfill({ json: { schemaVersion: '1.0', threads: [] } })
  );
  await page.route('**/api/executions', (route) =>
    route.fulfill({ json: { schemaVersion: '1.0', executions: [] } })
  );
  await page.route('**/api/health/services', (route) =>
    route.fulfill({ json: { checkedAt: new Date().toISOString(), services: [] } })
  );

  await page.goto('/');
  await page.getByLabel('Username').fill('scientist');
  await page.getByLabel('Password').fill('demo123');
  await page.getByRole('button', { name: 'Sign in' }).click();

  await expect(page.getByText('Ada Yönetici')).toBeVisible();
  expect(submitted).toEqual({ username: 'scientist', password: 'demo123' });
  expect(page.url()).not.toContain('keycloak');
});

test('authenticated shell exposes role-aware navigation and theme/language controls', async ({ page }) => {
  await authenticate(page);
  await page.route('**/api/chat/threads', (route) =>
    route.fulfill({ json: { schemaVersion: '1.0', threads: [] } })
  );
  await page.goto('/chat');

  await expect(page.locator('[data-slot="sidebar"]')).toBeVisible();
  await expect(page.locator('[data-slot="sidebar-content"]')).toBeVisible();
  await expect(page.locator('[data-slot="sidebar-footer"]')).toBeVisible();
  await expect(page.getByText('Ada Yönetici')).toBeVisible();
  await expect(page.getByRole('link', { name: 'Jupyter' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Ayarlar' })).toBeVisible();
  await page.getByRole('button', { name: 'Dil' }).click();
  await page.getByRole('menuitem', { name: 'English' }).click();
  await expect(page.getByRole('link', { name: 'Settings' })).toBeVisible();
  await expect(page.getByText('Your data stays in the controlled environment')).toBeVisible();
  await expect(page.locator('html')).toHaveAttribute('lang', 'en');
  await page.getByRole('button', { name: 'Change theme' }).click();
  await expect(page.locator('html')).toHaveClass(/dark/);
});

test('data entities shows the completed governed Sales dataset', async ({ page }) => {
  await authenticate(page);
  await page.route('**/api/chat/threads', (route) =>
    route.fulfill({ json: { schemaVersion: '1.0', threads: [] } })
  );
  await page.route('**/api/entities', (route) =>
    route.fulfill({
      json: {
        schemaVersion: '1.0',
        entities: [{
          id: '11111111-1111-4111-8111-111111111111',
          name: 'Sales',
          description: 'Deterministic governed sales demo dataset',
          status: 'ACTIVE',
          schemaRegistered: true,
          latestImportStatus: 'COMPLETED',
          governedRowCount: 50000
        }]
      }
    })
  );

  await page.goto('/entities');

  const salesCard = page.getByRole('link', { name: /Sales/ });
  await expect(salesCard.getByText('Sales', { exact: true })).toBeVisible();
  await expect(salesCard.getByText('COMPLETED').first()).toBeVisible();
  await expect(salesCard.getByText('50.000')).toBeVisible();
});

test('result page renders bounded facts and role-aware Jupyter guidance', async ({ page }) => {
  await authenticate(page);
  await page.route('**/api/executions/execution-1/result', (route) =>
    route.fulfill({
      json: {
        schemaVersion: '1.0',
        executionId: 'execution-1',
        rowCount: 1250,
        preview: [{ region: 'Marmara', revenue: 42000 }, { region: 'Ege', revenue: 31000 }],
        kpis: [{ label: 'Revenue', value: '₺73K' }],
        charts: [{ title: 'Revenue by region', labels: ['Marmara', 'Ege'], values: [42000, 31000], summary: 'Marmara is higher than Ege.' }],
        warnings: ['Preview is limited by policy.'],
        artifact: { artifactId: 'artifact-1', format: 'PARQUET', downloadAvailable: true, jupyterAvailable: true },
        guidanceKey: 'JUPYTER_AVAILABLE',
        summaryStatus: 'COMPLETED',
        resultSummary: 'Revenue is concentrated in Marmara.'
      }
    })
  );
  await page.goto('/results/execution-1');

  await expect(page.getByText('Revenue is concentrated in Marmara.')).toBeVisible();
  await expect(page.getByText('2 satır gösteriliyor; toplam 1250 satır.')).toBeVisible();
  await expect(page.getByRole('img', { name: 'Marmara is higher than Ege.' })).toBeVisible();
  await expect(page.getByLabel('Tam sonuç').getByRole('link', { name: /Jupyter/ })).toBeVisible();
});
