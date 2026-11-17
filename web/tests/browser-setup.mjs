/** Existing browser suites exercise the application with onboarding completed. */
export async function dismissInitialTutorial(page) {
  await page.addInitScript(() => localStorage.setItem('simenv.tutorial.v1.completed', 'true'))
}
