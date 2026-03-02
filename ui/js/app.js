/**
 * app.js — Entry point. Boots the entire SPA.
 */
import { initRouter, registerPage, navigate, guardUnload } from './router.js';
import { connectSSE }    from './sse.js';
import { setupAPI }      from './api.js';
import { applyBranding } from './utils.js';

import { init as initDashboard } from './pages/dashboard.js';
import { init as initSearch }    from './pages/search.js';
import { init as initLeads }     from './pages/leads.js';
import { init as initOutbox, isCampaignRunning } from './pages/outbox.js';
import { init as initReplies }   from './pages/replies.js';
import { init as initInboxes }   from './pages/inboxes.js';
import { init as initSettings }  from './pages/settings.js';
import { init as initPersona }   from './pages/persona.js';
import { init as initRecords }   from './pages/records.js';
import { init as initSequences } from './pages/sequences.js';

async function boot() {
  // Initialise every page module (each registers itself with the router)
  [
    initDashboard,
    initSearch,
    initLeads,
    initOutbox,
    initReplies,
    initInboxes,
    initSettings,
    initPersona,
    initRecords,
    initSequences,
  ].forEach((fn) => fn(registerPage));

  // Guard unload while a campaign is running
  guardUnload(isCampaignRunning);

  // Connect SSE live-updates
  connectSSE();

  // Load identity profile for white-label branding
  try {
    const data = await setupAPI.get();
    if (data?.profile) {
      applyBranding(data.profile);

      // First-run: no company name → go to Persona setup
      if (!data.profile.name) {
        showOnboardingBanner();
        initRouter();          // must init before navigating
        navigate('persona');
        return;
      }
    } else {
      showOnboardingBanner();
      initRouter();
      navigate('persona');
      return;
    }
  } catch {
    // Server not ready yet — still boot the router to show dashboard
  }

  // Kick off router (reads current hash or defaults to #dashboard)
  initRouter();
}

function showOnboardingBanner() {
  const banner = document.getElementById('onboarding-banner');
  if (banner) banner.style.display = 'flex';
}

// Run after DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', boot);
} else {
  boot();
}
