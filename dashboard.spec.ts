import { test, expect } from '@playwright/test';

test.describe('Yerevan Air Dashboard E2E', () => {
  // You can change this to your production URL: https://yerevan-air-production.up.railway.app
  const baseUrl = 'http://localhost:5000';

  test('Main dashboard loads and displays air quality metrics', async ({ page }) => {
    await page.goto(baseUrl);

    // 1. Verify page title and main header
    await expect(page).toHaveTitle(/Yerevan Air/);
    await expect(page.getByRole('heading', { name: 'YEREVAN AIR', level: 1 })).toBeVisible();

    // 2. Check for the Leaflet map container
    // Leaflet usually initializes in a div with id="map"
    const mapContainer = page.locator('#map');
    await expect(mapContainer).toBeVisible();

    // 3. Verify real-time metrics are populated (Temperature, Humidity, AQI)
    // These labels come from your renderer.py
    await expect(page.getByText('Average AQI')).toBeVisible();
    await expect(page.getByText('Temperature')).toBeVisible();
    await expect(page.getByText('Humidity')).toBeVisible();

    // 4. Verify station cards are rendered
    const stationCards = page.locator('.dist-card');
    await expect(stationCards.first()).toBeVisible();

    // 5. Test Ticker visibility
    await expect(page.locator('.ticker-item').first()).toBeVisible();
  });

  test('Health check endpoint returns operational status', async ({ request }) => {
    const response = await request.get(`${baseUrl}/health`);
    expect(response.ok()).toBeTruthy();
    
    const body = await response.json();
    expect(body).toMatchObject({
      status: 'ok',
      particles: expect.any(Number)
    });
  });

  test('Database export returns CSV file', async ({ page }) => {
    // Start waiting for download before clicking
    const downloadPromise = page.waitForEvent('download');
    await page.goto(`${baseUrl}/export-db`);
    const download = await downloadPromise;

    expect(download.suggestedFilename()).toBe('air_data.csv');
  });
});