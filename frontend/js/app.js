// Render Backend Connection Config
const RENDER_BACKEND_URL = 'https://phobiabot.onrender.com';

// Safe localStorage wrapper to prevent Mobile Safari / Private Browsing / sandboxed WebView exceptions
const storage = {
  get(key) {
    try {
      return (typeof window !== 'undefined' && window.localStorage) ? window.localStorage.getItem(key) : null;
    } catch (e) {
      return null;
    }
  },
  set(key, val) {
    try {
      if (typeof window !== 'undefined' && window.localStorage) window.localStorage.setItem(key, String(val));
    } catch (e) {}
  },
  remove(key) {
    try {
      if (typeof window !== 'undefined' && window.localStorage) window.localStorage.removeItem(key);
    } catch (e) {}
  }
};

function getApiBase() {
  const custom = storage.get('API_BASE_URL');
  if (custom) return custom.replace(/\/+$/, '');
  const host = window.location.hostname;
  if (host === 'localhost' || host === '127.0.0.1' || host.includes('onrender.com')) {
    return '';
  }
  return RENDER_BACKEND_URL;
}

const API_BASE = getApiBase();

// Intercept relative /api/ requests so Vercel forwards directly to Render
if (API_BASE) {
  const originalFetch = window.fetch;
  window.fetch = function (resource, init) {
    if (typeof resource === 'string' && resource.startsWith('/api/')) {
      resource = API_BASE + resource;
    }
    return originalFetch.call(this, resource, init);
  };
}

// State Store
const state = {
  status: null,
  templates: [],
  groups: [],
  campaigns: [],
  leads: [],
  keywords: [],
  logs: [],
  currentTab: 'tab-dashboard'
};

// Initialization on DOM Ready
document.addEventListener('DOMContentLoaded', () => {
  setupNavigation();

  // Auto-fill credential fields from browser storage if present
  try {
    const savedApiId = storage.get('TG_API_ID');
    const savedApiHash = storage.get('TG_API_HASH');
    const savedPhone = storage.get('TG_PHONE');
    const apiIdEl = document.getElementById('apiIdInput');
    const apiHashEl = document.getElementById('apiHashInput');
    const phoneEl = document.getElementById('phoneInput');
    if (savedApiId && apiIdEl) apiIdEl.value = savedApiId;
    if (savedApiHash && apiHashEl) apiHashEl.value = savedApiHash;
    if (savedPhone && phoneEl) phoneEl.value = savedPhone;
  } catch (e) {}

  // Immediate rendering of fast metrics so mobile screen displays in ~100ms
  loadStats();
  loadLogs();
  checkStatus();

  // Parallel background refresh of full data
  refreshAll();
  
  // Background polling for logs and stats every 4 seconds
  setInterval(() => {
    loadLogs();
    loadStats();
  }, 4000);
});

// Navigation Handling
function setupNavigation() {
  const tabs = document.querySelectorAll('.nav-tab');
  tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      const target = tab.getAttribute('data-tab');
      switchTab(target);
      // Auto-close mobile drawer when user taps a navigation link
      const sidebar = document.getElementById('sidebar');
      if (window.innerWidth < 768 && sidebar) {
        sidebar.classList.add('hidden');
      }
    });
  });

  const mobileBtn = document.getElementById('mobileMenuBtn');
  const sidebar = document.getElementById('sidebar');
  if (mobileBtn && sidebar) {
    mobileBtn.addEventListener('click', () => {
      sidebar.classList.toggle('hidden');
    });
  }
}

function switchTab(tabId) {
  state.currentTab = tabId;
  document.querySelectorAll('.tab-content').forEach(el => el.classList.add('hidden'));
  const activeContent = document.getElementById(tabId);
  if (activeContent) activeContent.classList.remove('hidden');

  document.querySelectorAll('.nav-tab').forEach(tab => {
    if (tab.getAttribute('data-tab') === tabId) {
      tab.classList.add('active');
    } else {
      tab.classList.remove('active');
    }
  });

  // Lazy loaders based on active tab
  if (tabId === 'tab-templates') loadTemplates();
  if (tabId === 'tab-poster') { loadCampaigns(); loadGroups(); loadTemplates(); }
  if (tabId === 'tab-scout') loadKeywords();
  if (tabId === 'tab-leads') loadLeads();
  if (tabId === 'tab-settings') checkStatus();
}

// Notification Banner
function showNotification(message, type = 'info') {
  const banner = document.getElementById('globalNotification');
  const icon = document.getElementById('notifIcon');
  const msgEl = document.getElementById('notifMessage');

  banner.className = `mb-6 p-4 rounded-xl flex items-center justify-between border text-sm transition-all duration-300`;

  if (type === 'success') {
    banner.classList.add('bg-emerald-950/60', 'border-emerald-600/50', 'text-emerald-200');
    icon.className = 'fa-solid fa-circle-check text-emerald-400 text-lg';
  } else if (type === 'error') {
    banner.classList.add('bg-rose-950/60', 'border-rose-600/50', 'text-rose-200');
    icon.className = 'fa-solid fa-circle-exclamation text-rose-400 text-lg';
  } else if (type === 'warning') {
    banner.classList.add('bg-amber-950/60', 'border-amber-600/50', 'text-amber-200');
    icon.className = 'fa-solid fa-triangle-exclamation text-amber-400 text-lg';
  } else {
    banner.classList.add('bg-cyan-950/60', 'border-cyan-600/50', 'text-cyan-200');
    icon.className = 'fa-solid fa-circle-info text-cyan-400 text-lg';
  }

  msgEl.innerText = message;
  banner.classList.remove('hidden');

  setTimeout(() => {
    banner.classList.add('hidden');
  }, 6000);
}

function hideNotification() {
  document.getElementById('globalNotification').classList.add('hidden');
}

// Refresh Everything Concurrently Without Blocking
async function refreshAll() {
  await Promise.allSettled([
    checkStatus(),
    loadStats(),
    loadLogs(),
    loadTemplates(),
    loadCampaigns(),
    loadLeads(),
    loadKeywords(),
    loadGroups()
  ]);
}

async function refreshDashboard() {
  await refreshAll();
  showNotification('Dashboard data refreshed', 'success');
}

// ----------------- AUTH & STATUS -----------------
async function checkStatus() {
  try {
    const res = await fetch('/api/status');
    if (!res.ok) return;
    const data = await res.json();
    state.status = data;

    const tg = data.telegram || {};
    const unauthAlert = document.getElementById('unauthAlert');
    const sidebarDot = document.getElementById('accountStatusDot');
    const sidebarName = document.getElementById('accountName');
    const sidebarSub = document.getElementById('accountSub');

    const setupDot = document.getElementById('setupDot');
    const setupTitle = document.getElementById('setupStatusTitle');
    const setupDesc = document.getElementById('setupStatusDesc');
    const btnLogout = document.getElementById('btnLogout');

    if (tg.is_authorized && tg.user) {
      if (unauthAlert) unauthAlert.classList.add('hidden');
      
      if (sidebarDot) sidebarDot.className = 'w-3 h-3 rounded-full bg-brand-400 pulse-emerald';
      if (sidebarName) sidebarName.innerText = tg.user.first_name + (tg.user.username ? ` (@${tg.user.username})` : '');
      if (sidebarSub) sidebarSub.innerText = tg.user.phone ? `+${tg.user.phone}` : 'Connected';

      if (setupDot) setupDot.className = 'w-3.5 h-3.5 rounded-full bg-brand-400';
      if (setupTitle) setupTitle.innerText = 'Connected';
      if (setupDesc) setupDesc.innerText = `Logged in as ${tg.user.first_name} (@${tg.user.username || 'No Handle'})`;
      if (btnLogout) btnLogout.classList.remove('hidden');

      if (tg.api_id) {
        const el = document.getElementById('apiIdInput');
        if (el) el.value = tg.api_id;
        storage.set('TG_API_ID', tg.api_id);
      }
      if (tg.phone) {
        const el = document.getElementById('phoneInput');
        if (el) el.value = tg.phone;
        storage.set('TG_PHONE', tg.phone);
      }
      if (tg.session_string) {
        storage.set('TG_SESSION_STRING', tg.session_string);
      }
      storage.set('TG_USER_INFO', JSON.stringify(tg.user));
    } else {
      // Auto-restore session from browser storage if server rebooted or spun down
      const savedSession = storage.get('TG_SESSION_STRING');
      let savedUser = null;
      try {
        savedUser = JSON.parse(storage.get('TG_USER_INFO') || 'null');
      } catch (e) {}
      
      if (savedSession) {
        // User IS logged in permanently in browser! Keep UI connected!
        if (unauthAlert) unauthAlert.classList.add('hidden');
        if (btnLogout) btnLogout.classList.remove('hidden');
        if (savedUser) {
          if (sidebarDot) sidebarDot.className = 'w-3 h-3 rounded-full bg-brand-400 pulse-emerald';
          if (sidebarName) sidebarName.innerText = savedUser.first_name + (savedUser.username ? ` (@${savedUser.username})` : '');
          if (sidebarSub) sidebarSub.innerText = savedUser.phone ? `+${savedUser.phone}` : 'Connected';
          if (setupDot) setupDot.className = 'w-3.5 h-3.5 rounded-full bg-brand-400';
          if (setupTitle) setupTitle.innerText = 'Connected';
          if (setupDesc) setupDesc.innerText = `Logged in as ${savedUser.first_name} (@${savedUser.username || 'No Handle'})`;
        }

        if (!state._isRestoringSession) {
          state._isRestoringSession = true;
          fetch('/api/auth/restore-session', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              session_string: savedSession,
              api_id: storage.get('TG_API_ID') ? parseInt(storage.get('TG_API_ID')) : undefined,
              api_hash: storage.get('TG_API_HASH') || undefined,
              phone: storage.get('TG_PHONE') || undefined
            })
          }).then(r => r.json()).then(resData => {
            if (resData.success) {
              loadGroups();
            }
          }).catch(e => {
            console.warn('Auto restore background notice:', e);
          }).finally(() => {
            setTimeout(() => { state._isRestoringSession = false; }, 8000);
          });
        }
        return;
      }

      if (unauthAlert) unauthAlert.classList.remove('hidden');

      if (sidebarDot) sidebarDot.className = 'w-3 h-3 rounded-full bg-amber-500';
      if (sidebarName) sidebarName.innerText = 'Not Connected';
      if (sidebarSub) sidebarSub.innerText = 'Connect Telegram';

      if (setupDot) setupDot.className = 'w-3.5 h-3.5 rounded-full bg-slate-500';
      if (setupTitle) setupTitle.innerText = 'Disconnected';
      if (setupDesc) setupDesc.innerText = 'Enter your Telegram credentials below to sign in.';
      if (btnLogout) btnLogout.classList.add('hidden');
    }

    // Live scout button state
    if (data.live_scout_active !== undefined) {
      updateLiveScoutUI(data.live_scout_active);
    }

  } catch (err) {
    console.error('Status check failed:', err);
  }
}

async function handleSendCode(e) {
  e.preventDefault();
  const apiId = document.getElementById('apiIdInput')?.value;
  const apiHash = document.getElementById('apiHashInput')?.value;
  const phone = document.getElementById('phoneInput')?.value;

  if (apiId) storage.set('TG_API_ID', apiId);
  if (apiHash) storage.set('TG_API_HASH', apiHash);
  if (phone) storage.set('TG_PHONE', phone);

  const btn = document.getElementById('btnRequestCode');
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin mr-2"></i> Sending OTP...';
  }

  try {
    const res = await fetch('/api/auth/send-code', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ api_id: parseInt(apiId), api_hash: apiHash, phone })
    });
    const data = await res.json();
    if (res.ok) {
      showNotification('Verification code sent to your Telegram app!', 'success');
      openModal('otpModal');
    } else {
      showNotification(data.detail || data.error || 'Failed to request login code', 'error');
    }
  } catch (err) {
    showNotification(err.message, 'error');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = '<span>Send Login Code to Telegram</span> <i class="fa-solid fa-arrow-right"></i>';
    }
  }
}

async function handleVerifyCode(e) {
  e.preventDefault();
  const code = document.getElementById('otpCodeInput')?.value;
  const password = document.getElementById('twoFactorPasswordInput')?.value;
  const btn = document.getElementById('btnSubmitOtp');

  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin mr-2"></i> Verifying...';
  }

  try {
    const res = await fetch('/api/auth/verify-code', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code, password: password || null })
    });
    const data = await res.json();

    if (data.need_2fa) {
      const tfField = document.getElementById('twoFactorField');
      if (tfField) tfField.classList.remove('hidden');
      showNotification('Your account has Two-Factor Authentication. Please enter your 2FA password.', 'warning');
    } else if (data.success) {
      if (data.session_string) {
        storage.set('TG_SESSION_STRING', data.session_string);
      }
      const curApiId = document.getElementById('apiIdInput')?.value || storage.get('TG_API_ID');
      const curApiHash = document.getElementById('apiHashInput')?.value || storage.get('TG_API_HASH');
      const curPhone = document.getElementById('phoneInput')?.value || storage.get('TG_PHONE');
      if (curApiId) storage.set('TG_API_ID', curApiId);
      if (curApiHash) storage.set('TG_API_HASH', curApiHash);
      if (curPhone) storage.set('TG_PHONE', curPhone);

      closeModal('otpModal');
      showNotification(`Successfully logged into Telegram! Permanent session saved.`, 'success');
      await checkStatus();
      await loadGroups();
      await loadStats();
      switchTab('tab-dashboard');
    } else {
      showNotification(data.detail || data.error || 'Verification failed', 'error');
    }
  } catch (err) {
    showNotification(err.message, 'error');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = 'Confirm & Log In';
    }
  }
}

async function logoutTelegram() {
  if (!confirm('Are you sure you want to log out of Telegram?')) return;
  try {
    storage.remove('TG_SESSION_STRING');
    storage.remove('TG_USER_INFO');
    storage.remove('TG_API_ID');
    storage.remove('TG_API_HASH');
    storage.remove('TG_PHONE');
    const res = await fetch('/api/auth/logout', { method: 'POST' });
    const data = await res.json();
    if (data.success) {
      showNotification('Logged out successfully', 'info');
      await checkStatus();
    }
  } catch (err) {
    showNotification(err.message, 'error');
  }
}

// ----------------- TEMPLATES WITH INDESTRUCTIBLE MULTI-TIER PERSISTENCE -----------------
const TEMPLATES_STORAGE_KEY = 'PHOBIA_USER_TEMPLATES_BACKUP';

async function loadTemplates() {
  try {
    const res = await fetch('/api/templates');
    if (!res.ok) throw new Error('Templates endpoint returned ' + res.status);
    const serverTemplates = await res.json();
    
    // Read local browser backup safely
    let localBackup = [];
    try {
      localBackup = JSON.parse(storage.get(TEMPLATES_STORAGE_KEY) || '[]');
    } catch (e) {
      localBackup = [];
    }

    // Check if any template from browser local backup is missing on the server
    const serverNames = new Set((serverTemplates || []).map(t => (t.name || '').trim().toLowerCase()));
    const missingOnServer = localBackup.filter(lt => {
      const name = (lt.name || '').trim().toLowerCase();
      return name && !serverNames.has(name);
    });

    if (missingOnServer.length > 0) {
      console.log(`[Templates] Restoring ${missingOnServer.length} user templates to server...`);
      try {
        const syncRes = await fetch('/api/templates/sync', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ templates: localBackup })
        });
        const syncData = await syncRes.json();
        if (syncData.success && syncData.templates) {
          state.templates = syncData.templates;
          storage.set(TEMPLATES_STORAGE_KEY, JSON.stringify(state.templates));
          renderTemplatesList();
          renderTemplatePickers();
          return;
        }
      } catch (syncErr) {
        console.warn('Auto-sync error:', syncErr);
      }
    }

    // Update state and refresh local backup with server templates
    state.templates = serverTemplates || [];
    if (state.templates.length > 0) {
      const merged = [...state.templates];
      for (const lt of localBackup) {
        if (!merged.some(m => (m.name || '').trim().toLowerCase() === (lt.name || '').trim().toLowerCase())) {
          merged.push(lt);
        }
      }
      storage.set(TEMPLATES_STORAGE_KEY, JSON.stringify(merged));
    }
    
    renderTemplatesList();
    renderTemplatePickers();
  } catch (err) {
    console.error('Failed to load templates from server, falling back to local storage:', err);
    try {
      const localBackup = JSON.parse(storage.get(TEMPLATES_STORAGE_KEY) || '[]');
      if (localBackup.length > 0) {
        state.templates = localBackup;
        renderTemplatesList();
        renderTemplatePickers();
      }
    } catch (e) {}
  }
}

function renderTemplatesList() {
  const container = document.getElementById('templatesList');
  if (!container) return;

  if (state.templates.length === 0) {
    container.innerHTML = `
      <div class="col-span-full p-12 text-center text-slate-500 space-y-2 bg-darkCard border border-darkBorder rounded-2xl">
        <i class="fa-solid fa-layer-group text-3xl"></i>
        <p class="text-sm">No templates found. Click "Create Template" to add one!</p>
      </div>`;
    return;
  }

  container.innerHTML = state.templates.map(t => `
    <div class="bg-darkCard border border-darkBorder rounded-2xl p-5 flex flex-col justify-between card-hover space-y-4">
      <div class="space-y-2.5">
        <div class="flex items-center justify-between">
          <h4 class="font-bold text-sm text-white truncate">${escapeHtml(t.name)}</h4>
          <span class="text-[10px] bg-slate-800 text-slate-400 px-2 py-0.5 rounded-full font-mono">ID #${t.id}</span>
        </div>
        <p class="text-xs text-slate-300 font-mono line-clamp-4 bg-slate-900/60 p-3 rounded-xl border border-slate-800 whitespace-pre-wrap">${escapeHtml(t.content)}</p>
      </div>
      <div class="flex items-center justify-between pt-3 border-t border-darkBorder text-xs">
        <button onclick="previewSpintaxDirect(${t.id})" class="text-cyan-400 hover:text-cyan-300 font-semibold flex items-center gap-1.5">
          <i class="fa-solid fa-wand-magic-sparkles"></i> Test Spintax
        </button>
        <div class="flex space-x-2">
          <button onclick="openTemplateModal(${t.id})" class="text-slate-400 hover:text-white p-1">
            <i class="fa-solid fa-pen-to-square"></i>
          </button>
          <button onclick="deleteTemplateItem(${t.id})" class="text-rose-400 hover:text-rose-300 p-1">
            <i class="fa-solid fa-trash-can"></i>
          </button>
        </div>
      </div>
    </div>
  `).join('');
}

function renderTemplatePickers() {
  // Quick Broadcast template select dropdown
  const quickTplSelect = document.getElementById('quickTemplateSelect');
  if (quickTplSelect) {
    quickTplSelect.innerHTML = '<option value="all">🔄 Rotate Across All Saved Templates (Spintax)</option>' +
      state.templates.map(t => `<option value="${t.id}">${escapeHtml(t.name)}</option>`).join('');
  }

  // Test Post select dropdown
  const testSelect = document.getElementById('testPostTemplateSelect');
  if (testSelect) {
    testSelect.innerHTML = state.templates.map(t => `
      <option value="${t.id}">${escapeHtml(t.name)}</option>
    `).join('');
  }

  // Campaign template checkboxes
  const campContainer = document.getElementById('campTemplatesContainer');
  if (campContainer) {
    campContainer.innerHTML = state.templates.map(t => `
      <label class="flex items-center space-x-2.5 p-2 rounded-lg hover:bg-slate-800 cursor-pointer">
        <input type="checkbox" name="campTemplate" value="${t.id}" class="rounded bg-slate-900 border-darkBorder text-brand-500 focus:ring-0" />
        <span class="text-xs text-slate-200 font-medium">${escapeHtml(t.name)}</span>
      </label>
    `).join('');
  }
}

function openTemplateModal(templateId = null) {
  document.getElementById('editTemplateId').value = templateId || '';
  document.getElementById('tplPreviewBox').classList.add('hidden');

  if (templateId) {
    const t = state.templates.find(item => item.id === templateId);
    if (t) {
      document.getElementById('templateModalTitle').innerText = 'Edit Template';
      document.getElementById('tplNameInput').value = t.name;
      document.getElementById('tplContentInput').value = t.content;
    }
  } else {
    document.getElementById('templateModalTitle').innerText = 'Create Content Template';
    document.getElementById('tplNameInput').value = '';
    document.getElementById('tplContentInput').value = '';
  }
  openModal('templateModal');
}

async function testSpintaxPreview() {
  const content = document.getElementById('tplContentInput').value;
  if (!content.trim()) return;

  try {
    const res = await fetch('/api/templates/preview', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content })
    });
    const data = await res.json();
    document.getElementById('tplPreviewText').innerText = data.rendered;
    document.getElementById('tplPreviewBox').classList.remove('hidden');
  } catch (err) {
    showNotification('Preview generation failed', 'error');
  }
}

async function previewSpintaxDirect(templateId) {
  const t = state.templates.find(item => item.id === templateId);
  if (!t) return;
  try {
    const res = await fetch('/api/templates/preview', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content: t.content })
    });
    const data = await res.json();
    alert(`Rendered Spintax Sample:\n\n${data.rendered}`);
  } catch (err) {
    showNotification(err.message, 'error');
  }
}

async function saveTemplate() {
  const editId = document.getElementById('editTemplateId')?.value;
  const name = document.getElementById('tplNameInput')?.value?.trim();
  const content = document.getElementById('tplContentInput')?.value?.trim();

  if (!name || !content) {
    showNotification('Template name and content are required', 'warning');
    return;
  }

  // Tier 1: Immediately save to safe browser storage so it's NEVER lost
  try {
    let localBackup = JSON.parse(storage.get(TEMPLATES_STORAGE_KEY) || '[]');
    if (editId) {
      const idx = localBackup.findIndex(t => String(t.id) === String(editId) || (t.name || '').toLowerCase() === name.toLowerCase());
      if (idx >= 0) {
        localBackup[idx].name = name;
        localBackup[idx].content = content;
        localBackup[idx].updated_at = new Date().toISOString();
      } else {
        localBackup.push({ name, content, updated_at: new Date().toISOString() });
      }
    } else {
      localBackup.push({ name, content, created_at: new Date().toISOString(), updated_at: new Date().toISOString() });
    }
    storage.set(TEMPLATES_STORAGE_KEY, JSON.stringify(localBackup));
  } catch (e) {
    console.warn('Storage save warning:', e);
  }

  const url = editId ? `/api/templates/${editId}` : '/api/templates';
  const method = editId ? 'PUT' : 'POST';

  try {
    const res = await fetch(url, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, content })
    });
    if (res.ok) {
      closeModal('templateModal');
      showNotification(`Template "${name}" saved and permanently preserved!`, 'success');
      await loadTemplates();
      await loadStats();
    } else {
      // If direct route failed, fallback to auto-sync endpoint
      const syncRes = await fetch('/api/templates/sync', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          templates: [{ name, content }]
        })
      });
      if (syncRes.ok) {
        closeModal('templateModal');
        showNotification(`Template "${name}" saved and synced permanently!`, 'success');
        await loadTemplates();
      } else {
        const err = await res.json();
        showNotification(err.detail || 'Failed to save template', 'error');
      }
    }
  } catch (err) {
    closeModal('templateModal');
    showNotification(`Template "${name}" saved to browser backup! Will sync to server when connected.`, 'info');
    await loadTemplates();
  }
}

async function deleteTemplateItem(id) {
  const t = state.templates.find(item => item.id === id);
  const tName = t ? t.name : 'this template';
  if (!confirm(`Are you sure you want to delete "${tName}"?`)) return;

  // Remove from storage
  try {
    let localBackup = JSON.parse(storage.get(TEMPLATES_STORAGE_KEY) || '[]');
    localBackup = localBackup.filter(item => item.id !== id && (item.name || '').toLowerCase() !== (tName || '').toLowerCase());
    storage.set(TEMPLATES_STORAGE_KEY, JSON.stringify(localBackup));
  } catch (e) {}

  try {
    const res = await fetch(`/api/templates/${id}`, { method: 'DELETE' });
    if (res.ok) {
      showNotification('Template deleted', 'info');
      await loadTemplates();
      await loadStats();
    }
  } catch (err) {
    showNotification(err.message, 'error');
  }
}

function exportTemplatesBackup() {
  const templates = state.templates.length > 0 ? state.templates : JSON.parse(storage.get(TEMPLATES_STORAGE_KEY) || '[]');
  if (templates.length === 0) {
    showNotification('No templates found to export', 'warning');
    return;
  }
  const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(templates, null, 2));
  const downloadAnchor = document.createElement('a');
  downloadAnchor.setAttribute("href", dataStr);
  downloadAnchor.setAttribute("download", `phobiabot_templates_backup_${new Date().toISOString().slice(0,10)}.json`);
  document.body.appendChild(downloadAnchor);
  downloadAnchor.click();
  downloadAnchor.remove();
  showNotification('Templates exported to JSON file successfully!', 'success');
}

function triggerImportTemplates() {
  const input = document.getElementById('importTemplatesInput');
  if (input) input.click();
}

async function handleImportTemplates(event) {
  const file = event.target.files && event.target.files[0];
  if (!file) return;

  const reader = new FileReader();
  reader.onload = async (e) => {
    try {
      const imported = JSON.parse(e.target.result);
      if (!Array.isArray(imported)) {
        showNotification('Invalid file format. Expected a JSON array of templates.', 'error');
        return;
      }
      const syncRes = await fetch('/api/templates/sync', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ templates: imported })
      });
      const data = await syncRes.json();
      if (data.success) {
        showNotification(`Successfully imported and restored ${imported.length} templates!`, 'success');
        await loadTemplates();
      } else {
        showNotification('Import failed on server', 'error');
      }
    } catch (err) {
      showNotification('Error reading template backup file: ' + err.message, 'error');
    }
  };
  reader.readAsText(file);
  event.target.value = '';
}

// ----------------- GROUPS -----------------
async function loadGroups() {
  try {
    const res = await fetch('/api/groups');
    const data = await res.json();
    state.groups = data.groups || [];
    renderGroupPickers();
  } catch (err) {
    console.error('Failed to load groups:', err);
  }
}

function renderGroupPickers() {
  // Update group count badges across dashboard and auto-poster
  const totalCount = state.groups.length;
  const posterBadge = document.getElementById('posterTotalGroupsBadge');
  const targetCountText = document.getElementById('quickTargetCountText');
  const kpiGroups = document.getElementById('kpiGroups');
  if (posterBadge) posterBadge.innerText = `${totalCount} Groups`;
  if (targetCountText) targetCountText.innerText = totalCount;
  if (kpiGroups) kpiGroups.innerText = totalCount;

  // Test Post Target Group Dropdown
  const testGroupSelect = document.getElementById('testPostGroupSelect');
  if (testGroupSelect) {
    testGroupSelect.innerHTML = state.groups.map(g => `
      <option value="${g.id}">${escapeHtml(g.title)} (${g.member_count || 0} members)</option>
    `).join('');
  }

  // Campaign Group Checkboxes
  const campGroups = document.getElementById('campGroupsContainer');
  if (campGroups) {
    if (state.groups.length === 0) {
      campGroups.innerHTML = `<p class="p-3 text-slate-500 text-center text-xs">No groups found. Make sure your Telegram account is connected.</p>`;
      return;
    }

    campGroups.innerHTML = state.groups.map(g => `
      <label class="flex items-center space-x-2.5 p-2 rounded-lg hover:bg-slate-800 cursor-pointer">
        <input type="checkbox" name="campGroup" value="${g.id}" class="rounded bg-slate-900 border-darkBorder text-brand-500 focus:ring-0" />
        <span class="text-xs text-slate-200 truncate flex-1">${escapeHtml(g.title)}</span>
        <span class="text-[10px] text-slate-400 bg-slate-800 px-1.5 py-0.5 rounded">${g.member_count || 0} users</span>
      </label>
    `).join('');
  }
}

function selectAllGroups(checked) {
  const checkboxes = document.querySelectorAll('input[name="campGroup"]');
  checkboxes.forEach(cb => cb.checked = checked);
}

// ----------------- QUICK ALL-GROUPS BROADCASTER -----------------
function setQuickInterval(val, unit) {
  const valInput = document.getElementById('quickIntervalVal');
  const unitSelect = document.getElementById('quickIntervalUnit');
  if (valInput) valInput.value = val;
  if (unitSelect) unitSelect.value = unit;
  showNotification(`Posting schedule set to: every ${val} ${unit}`, 'info');
}

async function startQuickBroadcast() {
  const btn = document.getElementById('btnQuickStartBroadcast');
  const val = parseInt(document.getElementById('quickIntervalVal').value) || 30;
  const unit = document.getElementById('quickIntervalUnit').value || 'minutes';
  const tplVal = document.getElementById('quickTemplateSelect').value;
  const delayMin = parseInt(document.getElementById('quickDelayMin').value) || 10;
  const delayMax = parseInt(document.getElementById('quickDelayMax').value) || 30;

  if (state.groups.length === 0) {
    showNotification('No Telegram groups found! Please connect your Telegram account first.', 'warning');
    return;
  }

  let templateIds = null;
  if (tplVal !== 'all') {
    templateIds = [parseInt(tplVal)];
  }

  btn.disabled = true;
  btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin mr-2"></i> Launching Auto-Broadcaster...';

  try {
    const res = await fetch('/api/campaigns/quick-start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: `All-Groups Broadcast (${val} ${unit})`,
        template_ids: templateIds,
        interval_val: val,
        interval_unit: unit,
        post_to_all: true,
        delay_min: delayMin,
        delay_max: delayMax
      })
    });
    const data = await res.json();
    if (res.ok && data.success) {
      showNotification(`🚀 Auto-Posting Started! Broadcasting to all ${state.groups.length} groups every ${val} ${unit}.`, 'success');
      await loadCampaigns();
      await loadStats();
      await loadLogs();
    } else {
      showNotification(data.detail || data.error || 'Failed to start auto-poster', 'error');
    }
  } catch (err) {
    showNotification(err.message, 'error');
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<i class="fa-solid fa-play mr-2"></i> START AUTO-POSTING TO ALL GROUPS';
  }
}

async function pauseQuickBroadcast() {
  const activeCamp = state.campaigns.find(c => c.status === 'running');
  if (!activeCamp) {
    showNotification('No running campaign to pause.', 'info');
    return;
  }
  await pauseCampaign(activeCamp.id);
}

async function stopQuickBroadcast() {
  const activeCamp = state.campaigns.find(c => c.status === 'running' || c.status === 'paused');
  if (!activeCamp) {
    showNotification('No active campaign to stop.', 'info');
    return;
  }
  await stopCampaign(activeCamp.id);
}

// ----------------- AUTO-POSTER CAMPAIGNS -----------------
async function loadCampaigns() {
  try {
    const res = await fetch('/api/campaigns');
    state.campaigns = await res.json();
    renderCampaigns();
  } catch (err) {
    console.error('Failed to load campaigns:', err);
  }
}

function renderCampaigns() {
  // Update Quick Broadcast Status Box
  const activeCamp = state.campaigns.find(c => c.status === 'running') || state.campaigns.find(c => c.status === 'paused') || state.campaigns[0];
  const qBadge = document.getElementById('quickCampStatusBadge');
  const qPosts = document.getElementById('quickCampPostsCount');
  const qNext = document.getElementById('quickCampNextRun');
  if (activeCamp && qBadge) {
    if (activeCamp.status === 'running') {
      qBadge.className = 'font-bold text-emerald-300 bg-emerald-950/80 border border-emerald-800 px-2.5 py-0.5 rounded-full uppercase text-[10px] animate-pulse';
      qBadge.innerText = 'RUNNING';
    } else if (activeCamp.status === 'paused') {
      qBadge.className = 'font-bold text-amber-300 bg-amber-950/80 border border-amber-800 px-2.5 py-0.5 rounded-full uppercase text-[10px]';
      qBadge.innerText = 'PAUSED';
    } else {
      qBadge.className = 'font-bold text-slate-300 bg-slate-800 px-2.5 py-0.5 rounded-full uppercase text-[10px]';
      qBadge.innerText = 'STOPPED';
    }
    if (qPosts) qPosts.innerText = activeCamp.posts_sent || 0;
    if (qNext) {
      if (activeCamp.next_run && activeCamp.status === 'running') {
        const d = new Date(activeCamp.next_run);
        qNext.innerText = `${d.toLocaleTimeString()} (every ${activeCamp.interval_val} ${activeCamp.interval_unit})`;
      } else {
        qNext.innerText = activeCamp.status === 'running' ? 'Broadcasting...' : 'None';
      }
    }
  } else if (qBadge) {
    qBadge.className = 'font-bold text-slate-300 bg-slate-800 px-2.5 py-0.5 rounded-full uppercase text-[10px]';
    qBadge.innerText = 'IDLE';
    if (qPosts) qPosts.innerText = '0';
    if (qNext) qNext.innerText = 'None';
  }

  const container = document.getElementById('campaignsList');
  if (!container) return;

  if (state.campaigns.length === 0) {
    container.innerHTML = `
      <div class="bg-darkCard border border-darkBorder p-8 rounded-2xl text-center text-slate-500 space-y-2">
        <i class="fa-solid fa-bullhorn text-3xl"></i>
        <p class="text-sm">No campaigns active. Click "New Campaign" to set up your automated schedule.</p>
      </div>`;
    return;
  }

  container.innerHTML = state.campaigns.map(c => {
    let statusBadge = '';
    if (c.status === 'running') {
      statusBadge = '<span class="px-2.5 py-1 rounded-full text-[10px] font-bold bg-emerald-500/20 text-emerald-400 flex items-center gap-1.5"><span class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span> RUNNING</span>';
    } else if (c.status === 'paused') {
      statusBadge = '<span class="px-2.5 py-1 rounded-full text-[10px] font-bold bg-amber-500/20 text-amber-400">PAUSED</span>';
    } else {
      statusBadge = '<span class="px-2.5 py-1 rounded-full text-[10px] font-bold bg-slate-800 text-slate-400">STOPPED</span>';
    }

    const tplCount = JSON.parse(c.template_ids || '[]').length;
    const grpCount = JSON.parse(c.target_group_ids || '[]').length;

    return `
      <div class="bg-darkCard border border-darkBorder rounded-2xl p-5 flex flex-col md:flex-row md:items-center justify-between gap-4 card-hover">
        <div class="space-y-1.5">
          <div class="flex items-center space-x-3">
            <h4 class="font-bold text-base text-white">${escapeHtml(c.name)}</h4>
            ${statusBadge}
          </div>
          <div class="flex flex-wrap items-center gap-3 text-xs text-slate-400">
            <span><i class="fa-solid fa-clock text-slate-500 mr-1"></i> Every ${c.interval_val} ${c.interval_unit}</span>
            <span><i class="fa-solid fa-layer-group text-slate-500 mr-1"></i> ${tplCount} Templates</span>
            <span><i class="fa-solid fa-users text-slate-500 mr-1"></i> ${grpCount} Groups</span>
            <span class="text-brand-400 font-semibold"><i class="fa-solid fa-paper-plane mr-1"></i> ${c.posts_sent} Posts Sent</span>
          </div>
        </div>

        <div class="flex items-center space-x-2">
          ${c.status === 'running' 
            ? `<button onclick="pauseCampaign(${c.id})" class="px-3 py-1.5 rounded-xl bg-amber-500/20 hover:bg-amber-500/30 text-amber-400 text-xs font-bold transition flex items-center gap-1.5"><i class="fa-solid fa-pause"></i> Pause</button>`
            : `<button onclick="startCampaign(${c.id})" class="px-3.5 py-1.5 rounded-xl bg-brand-600 hover:bg-brand-500 text-white text-xs font-bold transition flex items-center gap-1.5"><i class="fa-solid fa-play"></i> Start</button>`
          }
          <button onclick="stopCampaign(${c.id})" class="px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-bold transition flex items-center gap-1.5">
            <i class="fa-solid fa-stop"></i> Stop
          </button>
        </div>
      </div>
    `;
  }).join('');
}

function openCampaignModal() {
  document.getElementById('campNameInput').value = 'Daily IPTV Broadcaster';
  selectAllGroups(false);
  openModal('campaignModal');
}

async function saveCampaign() {
  const name = document.getElementById('campNameInput').value;
  const intervalVal = parseInt(document.getElementById('campIntervalVal').value) || 30;
  const intervalUnit = document.getElementById('campIntervalUnit').value;
  const delayMin = parseInt(document.getElementById('campDelayMin').value) || 15;
  const delayMax = parseInt(document.getElementById('campDelayMax').value) || 45;

  const templateBoxes = document.querySelectorAll('input[name="campTemplate"]:checked');
  const template_ids = Array.from(templateBoxes).map(cb => parseInt(cb.value));

  const groupBoxes = document.querySelectorAll('input[name="campGroup"]:checked');
  const target_group_ids = Array.from(groupBoxes).map(cb => parseInt(cb.value));

  if (!name.trim()) {
    showNotification('Please enter a campaign name', 'warning');
    return;
  }
  if (template_ids.length === 0) {
    showNotification('Please select at least one template', 'warning');
    return;
  }
  if (target_group_ids.length === 0) {
    showNotification('Please select at least one target group', 'warning');
    return;
  }

  try {
    const res = await fetch('/api/campaigns', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name,
        template_ids,
        target_group_ids,
        interval_val: intervalVal,
        interval_unit: intervalUnit,
        delay_min: delayMin,
        delay_max: delayMax
      })
    });
    if (res.ok) {
      closeModal('campaignModal');
      showNotification('Campaign created successfully!', 'success');
      await loadCampaigns();
      await loadStats();
    } else {
      showNotification('Failed to create campaign', 'error');
    }
  } catch (err) {
    showNotification(err.message, 'error');
  }
}

async function startCampaign(id) {
  try {
    const res = await fetch(`/api/campaigns/${id}/start`, { method: 'POST' });
    if (res.ok) {
      showNotification('Campaign started!', 'success');
      await loadCampaigns();
      await loadStats();
    }
  } catch (err) {
    showNotification(err.message, 'error');
  }
}

async function pauseCampaign(id) {
  try {
    const res = await fetch(`/api/campaigns/${id}/pause`, { method: 'POST' });
    if (res.ok) {
      showNotification('Campaign paused', 'info');
      await loadCampaigns();
    }
  } catch (err) {
    showNotification(err.message, 'error');
  }
}

async function stopCampaign(id) {
  try {
    const res = await fetch(`/api/campaigns/${id}/stop`, { method: 'POST' });
    if (res.ok) {
      showNotification('Campaign stopped', 'info');
      await loadCampaigns();
    }
  } catch (err) {
    showNotification(err.message, 'error');
  }
}

async function runTestPost() {
  const templateId = document.getElementById('testPostTemplateSelect').value;
  const groupId = document.getElementById('testPostGroupSelect').value;
  const btn = document.getElementById('btnTestPost');

  if (!templateId || !groupId) {
    showNotification('Please select both a template and a target group', 'warning');
    return;
  }

  btn.disabled = true;
  btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin mr-2"></i> Sending...';

  try {
    const res = await fetch('/api/poster/test-post', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        template_id: parseInt(templateId),
        group_id: parseInt(groupId)
      })
    });
    const data = await res.json();
    if (data.success) {
      showNotification(`Test message sent to ${data.group_title}!`, 'success');
      await loadStats();
      await loadLogs();
    } else {
      showNotification(data.error || 'Test post failed', 'error');
    }
  } catch (err) {
    showNotification(err.message, 'error');
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<i class="fa-solid fa-bolt"></i> Send Test Now';
  }
}

// ----------------- IPTV LEAD SCOUT & KEYWORDS -----------------
async function loadKeywords() {
  try {
    const res = await fetch('/api/scout/keywords');
    state.keywords = await res.json();
    renderKeywordsChips();
  } catch (err) {
    console.error('Failed to load keywords:', err);
  }
}

function renderKeywordsChips() {
  const container = document.getElementById('keywordsChipsContainer');
  if (!container) return;

  container.innerHTML = state.keywords.map(kw => `
    <span class="inline-flex items-center space-x-1.5 px-3 py-1 rounded-full bg-slate-800 text-xs font-semibold text-slate-200 border border-slate-700">
      <span>${escapeHtml(kw)}</span>
      <button onclick="removeKeyword('${escapeHtml(kw)}')" class="text-slate-500 hover:text-rose-400 ml-1">
        <i class="fa-solid fa-xmark text-[10px]"></i>
      </button>
    </span>
  `).join('');
}

async function promptAddKeyword() {
  const word = prompt('Enter a new IPTV scout keyword (e.g. "stalker portal", "xtream code", "smart one iptv"):');
  if (!word || !word.trim()) return;

  const clean = word.trim().toLowerCase();
  if (state.keywords.includes(clean)) return;

  const updated = [...state.keywords, clean];
  try {
    const res = await fetch('/api/scout/keywords', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ keywords: updated })
    });
    if (res.ok) {
      state.keywords = updated;
      renderKeywordsChips();
      showNotification(`Keyword "${clean}" added`, 'success');
    }
  } catch (err) {
    showNotification(err.message, 'error');
  }
}

async function removeKeyword(word) {
  const updated = state.keywords.filter(k => k !== word);
  try {
    const res = await fetch('/api/scout/keywords', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ keywords: updated })
    });
    if (res.ok) {
      state.keywords = updated;
      renderKeywordsChips();
    }
  } catch (err) {
    showNotification(err.message, 'error');
  }
}

async function runScoutScan() {
  const rawLinks = document.getElementById('scoutLinksInput').value;
  const depth = parseInt(document.getElementById('scoutDepthSelect').value) || 200;
  const btn = document.getElementById('btnStartScout');

  const links = rawLinks.split(/[\n,]/).map(l => l.trim()).filter(l => l.length > 0);
  if (links.length === 0) {
    showNotification('Please enter at least one Telegram group or channel link', 'warning');
    return;
  }

  btn.disabled = true;
  btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin mr-2"></i> Scanning Messages...';

  try {
    const res = await fetch('/api/scout/scan', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        links,
        keywords: state.keywords,
        scan_depth: depth
      })
    });
    const data = await res.json();
    if (data.success) {
      showNotification(`Scout scan complete! Found ${data.total_leads_found} members talking about IPTV!`, 'success');
      await loadLeads();
      await loadStats();
      await loadLogs();

      // Render Scout Live Results Preview Box
      const resultsBox = document.getElementById('scoutResultsBox');
      const resultsList = document.getElementById('scoutResultsList');
      const foundBadge = document.getElementById('scoutFoundBadge');

      if (resultsBox && resultsList) {
        resultsBox.classList.remove('hidden');
        if (foundBadge) foundBadge.innerText = `${data.total_leads_found} Leads Discovered`;

        // Gather all newly discovered leads from details or recent leads
        let allDiscovered = [];
        if (Array.isArray(data.details)) {
          data.details.forEach(d => {
            if (Array.isArray(d.leads)) allDiscovered.push(...d.leads);
          });
        }
        if (allDiscovered.length === 0 && state.leads.length > 0) {
          allDiscovered = state.leads.slice(0, 10);
        }

        if (allDiscovered.length === 0) {
          resultsList.innerHTML = `
            <div class="p-6 text-center text-slate-500 text-xs">
              No new messages matched IPTV keywords in this scan. Try scanning more messages or adding custom keywords.
            </div>`;
        } else {
          resultsList.innerHTML = allDiscovered.map(lead => {
            const fullName = `${lead.first_name || ''} ${lead.last_name || ''}`.trim() || 'Telegram User';
            const dmLink = lead.username 
              ? `<a href="https://t.me/${lead.username}" target="_blank" class="px-3 py-1.5 rounded-xl bg-cyan-500/20 hover:bg-cyan-500/30 text-cyan-300 font-bold text-xs flex items-center gap-1.5 transition">
                   <i class="fa-brands fa-telegram"></i> DM @${escapeHtml(lead.username)}
                 </a>`
              : `<span class="text-[11px] text-slate-500 font-mono">ID: ${lead.user_id}</span>`;

            return `
              <div class="p-4 rounded-xl bg-slate-950/80 border border-darkBorder flex flex-col md:flex-row md:items-center justify-between gap-3 hover:border-brand-500/40 transition">
                <div class="space-y-1 flex-1">
                  <div class="flex items-center gap-2">
                    <span class="font-bold text-white text-sm">${escapeHtml(fullName)}</span>
                    <span class="px-2 py-0.5 rounded-md bg-brand-950 text-brand-300 text-[10px] font-bold border border-brand-800 uppercase">${escapeHtml(lead.matched_keyword)}</span>
                    <span class="text-[11px] text-slate-500"><i class="fa-solid fa-users text-[10px] mr-1"></i>${escapeHtml(lead.group_title || 'Group')}</span>
                  </div>
                  <p class="text-xs text-slate-300 italic bg-slate-900/60 p-2 rounded-lg border border-darkBorder/40">"${escapeHtml(lead.message_text || '')}"</p>
                  <p class="text-[10px] text-slate-500">${lead.detected_at || ''}</p>
                </div>
                <div class="flex-shrink-0">
                  ${dmLink}
                </div>
              </div>`;
          }).join('');
        }
      }

    } else {
      showNotification(data.error || 'Scout scan failed', 'error');
    }
  } catch (err) {
    showNotification(err.message, 'error');
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<i class="fa-solid fa-magnifying-glass-plus"></i> Scout All Members Talking About IPTV';
  }
}

async function toggleLiveScout() {
  const current = state.status?.live_scout_active || false;
  const target = !current;

  try {
    const res = await fetch('/api/scout/live-toggle', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled: target })
    });
    const data = await res.json();
    if (data.success) {
      updateLiveScoutUI(target);
      showNotification(`Live Scout Monitor ${target ? 'ACTIVATED' : 'PAUSED'}`, target ? 'success' : 'info');
      if (state.status) state.status.live_scout_active = target;
    }
  } catch (err) {
    showNotification(err.message, 'error');
  }
}

function updateLiveScoutUI(isActive) {
  const text = document.getElementById('liveMonitorStatusText');
  const btn = document.getElementById('btnToggleLiveScout');
  if (!text || !btn) return;

  if (isActive) {
    text.innerText = '● LIVE LISTENING';
    text.className = 'text-xs font-bold text-brand-400 animate-pulse';
    btn.innerText = 'Pause Monitor';
    btn.className = 'px-5 py-2.5 rounded-xl bg-rose-600 hover:bg-rose-500 text-white text-xs font-bold uppercase tracking-wider transition';
  } else {
    text.innerText = 'OFFLINE';
    text.className = 'text-xs font-bold text-slate-500';
    btn.innerText = 'Enable Live Monitor';
    btn.className = 'px-5 py-2.5 rounded-xl bg-brand-600 hover:bg-brand-500 text-white text-xs font-bold uppercase tracking-wider transition';
  }
}

// ----------------- LEADS DATABASE -----------------
let searchDebounceTimer = null;
function debounceFilterLeads() {
  clearTimeout(searchDebounceTimer);
  searchDebounceTimer = setTimeout(loadLeads, 300);
}

async function loadLeads() {
  const searchInput = document.getElementById('leadSearchInput');
  const statusFilter = document.getElementById('leadStatusFilter');
  const keyword = searchInput ? searchInput.value.trim() : '';
  const status = statusFilter ? statusFilter.value : 'all';

  const params = new URLSearchParams();
  if (keyword) params.append('keyword', keyword);
  if (status && status !== 'all') params.append('status', status);

  try {
    const res = await fetch(`/api/scout/leads?${params.toString()}`);
    state.leads = await res.json();
    renderLeads();
  } catch (err) {
    console.error('Failed to load leads:', err);
  }
}

function renderLeads() {
  const tbody = document.getElementById('leadsTableBody');
  const empty = document.getElementById('emptyLeadsMessage');
  const countBadge = document.getElementById('badgeLeadCount');

  if (countBadge) countBadge.innerText = state.leads.length;

  if (!tbody) return;

  if (state.leads.length === 0) {
    tbody.innerHTML = '';
    if (empty) empty.classList.remove('hidden');
    return;
  }
  if (empty) empty.classList.add('hidden');

  tbody.innerHTML = state.leads.map(lead => {
    const usernameTag = lead.username 
      ? `<a href="https://t.me/${lead.username}" target="_blank" class="text-cyan-400 hover:underline font-semibold flex items-center gap-1"><i class="fa-brands fa-telegram"></i> @${escapeHtml(lead.username)}</a>`
      : `<span class="text-slate-400 font-mono text-[11px]">ID: ${lead.user_id}</span>`;

    const fullName = `${lead.first_name || ''} ${lead.last_name || ''}`.trim() || 'Anonymous User';

    return `
      <tr class="hover:bg-slate-900/50 transition">
        <td class="p-3.5">
          <div class="font-semibold text-white">${escapeHtml(fullName)}</div>
          <div>${usernameTag}</div>
        </td>
        <td class="p-3.5">
          <div class="font-medium text-slate-300 max-w-[140px] truncate" title="${escapeHtml(lead.group_title)}">${escapeHtml(lead.group_title || 'Group')}</div>
        </td>
        <td class="p-3.5">
          <span class="px-2.5 py-1 rounded-full text-[11px] font-bold bg-brand-500/10 text-brand-400 border border-brand-500/20">
            ${escapeHtml(lead.matched_keyword)}
          </span>
        </td>
        <td class="p-3.5">
          <p class="max-w-xs md:max-w-md line-clamp-2 text-slate-300" title="${escapeHtml(lead.message_text)}">
            ${escapeHtml(lead.message_text)}
          </p>
        </td>
        <td class="p-3.5 text-slate-400 whitespace-nowrap">
          ${lead.detected_at}
        </td>
        <td class="p-3.5">
          <select onchange="changeLeadStatus(${lead.id}, this.value)" class="bg-slate-900 border border-darkBorder rounded-lg px-2 py-1 text-[11px] text-slate-300 focus:outline-none">
            <option value="new" ${lead.status === 'new' ? 'selected' : ''}>New</option>
            <option value="contacted" ${lead.status === 'contacted' ? 'selected' : ''}>Contacted</option>
            <option value="converted" ${lead.status === 'converted' ? 'selected' : ''}>Converted</option>
            <option value="ignored" ${lead.status === 'ignored' ? 'selected' : ''}>Ignored</option>
          </select>
        </td>
        <td class="p-3.5 text-right whitespace-nowrap space-x-2">
          ${lead.username ? `
            <a href="https://t.me/${lead.username}" target="_blank" class="px-2.5 py-1 rounded-lg bg-cyan-500/20 text-cyan-400 hover:bg-cyan-500/30 font-semibold text-[11px] inline-flex items-center gap-1">
              <i class="fa-solid fa-paper-plane text-[10px]"></i> DM
            </a>
          ` : ''}
          <button onclick="deleteLeadItem(${lead.id})" class="text-slate-500 hover:text-rose-400 p-1">
            <i class="fa-solid fa-trash-can"></i>
          </button>
        </td>
      </tr>
    `;
  }).join('');
}

async function changeLeadStatus(leadId, newStatus) {
  try {
    await fetch(`/api/scout/leads/${leadId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: newStatus })
    });
    showNotification('Lead status updated', 'success');
  } catch (err) {
    showNotification(err.message, 'error');
  }
}

async function deleteLeadItem(leadId) {
  try {
    await fetch(`/api/scout/leads/${leadId}`, { method: 'DELETE' });
    await loadLeads();
    await loadStats();
  } catch (err) {
    showNotification(err.message, 'error');
  }
}

async function clearAllLeads() {
  if (!confirm('Are you sure you want to clear all discovered leads? This cannot be undone.')) return;
  try {
    await fetch('/api/scout/leads', { method: 'DELETE' });
    showNotification('All leads cleared', 'info');
    await loadLeads();
    await loadStats();
  } catch (err) {
    showNotification(err.message, 'error');
  }
}

// ----------------- STATS & LOGS -----------------
async function loadStats() {
  try {
    const res = await fetch('/api/stats');
    if (!res.ok) return;
    const data = await res.json();
    
    const kpiLeads = document.getElementById('kpiLeads');
    if (kpiLeads && data.leads_count !== undefined) kpiLeads.innerText = data.leads_count;
    
    const kpiPosts = document.getElementById('kpiPosts');
    if (kpiPosts && data.posts_sent !== undefined) kpiPosts.innerText = data.posts_sent;
    
    const kpiTemplates = document.getElementById('kpiTemplates');
    if (kpiTemplates && data.templates_count !== undefined) kpiTemplates.innerText = data.templates_count;
    
    const kpiActiveCampaigns = document.getElementById('kpiActiveCampaigns');
    if (kpiActiveCampaigns && data.active_campaigns !== undefined) kpiActiveCampaigns.innerText = data.active_campaigns;
    
    const kpiGroups = document.getElementById('kpiGroups');
    if (kpiGroups) {
      if (data.groups_count !== undefined && data.groups_count > 0) {
        kpiGroups.innerText = data.groups_count;
      } else if (state.groups.length > 0) {
        kpiGroups.innerText = state.groups.length;
      }
    }

    const badgeLead = document.getElementById('badgeLeadCount');
    if (badgeLead && data.leads_count !== undefined) badgeLead.innerText = data.leads_count;
  } catch (err) {
    console.error('Failed to load stats:', err);
  }
}

async function loadLogs() {
  try {
    const res = await fetch('/api/logs?limit=50');
    if (!res.ok) return;
    const logs = await res.json();
    const consoleEl = document.getElementById('logsConsole');
    if (!consoleEl) return;

    if (!Array.isArray(logs) || logs.length === 0) {
      consoleEl.innerHTML = `<div class="text-slate-500 italic">No logs recorded yet.</div>`;
      return;
    }

    consoleEl.innerHTML = logs.map(l => {
      let colorClass = 'text-slate-300';
      if (l.level === 'SUCCESS') colorClass = 'text-emerald-400';
      if (l.level === 'WARNING') colorClass = 'text-amber-400';
      if (l.level === 'ERROR') colorClass = 'text-rose-400 font-bold';

      return `
        <div class="leading-relaxed flex items-start space-x-2">
          <span class="text-slate-500 text-[10px] select-none">[${escapeHtml(l.timestamp || '')}]</span>
          <span class="text-[10px] px-1.5 rounded font-bold ${colorClass} bg-slate-900 border border-slate-800">[${escapeHtml(l.category || '')}]</span>
          <span class="${colorClass}">${escapeHtml(l.message || '')}</span>
        </div>
      `;
    }).join('');
  } catch (err) {
    console.error('Failed to load logs:', err);
  }
}

// ----------------- MODAL HELPERS -----------------
function openModal(id) {
  const m = document.getElementById(id);
  if (m) m.classList.remove('hidden');
}

function closeModal(id) {
  const m = document.getElementById(id);
  if (m) m.classList.add('hidden');
}

function escapeHtml(str) {
  if (!str) return '';
  return str.replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
}
