// Render Backend Connection Config
const RENDER_BACKEND_URL = 'https://phobiabot.onrender.com';

function getApiBase() {
  const custom = localStorage.getItem('API_BASE_URL');
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
document.addEventListener('DOMContentLoaded', async () => {
  setupNavigation();
  await refreshAll();
  
  // Background polling for logs and stats every 4 seconds
  setInterval(async () => {
    await loadLogs();
    await loadStats();
  }, 4000);
});

// Navigation Handling
function setupNavigation() {
  const tabs = document.querySelectorAll('.nav-tab');
  tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      const target = tab.getAttribute('data-tab');
      switchTab(target);
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

// Refresh Everything
async function refreshAll() {
  await checkStatus();
  await loadStats();
  await loadTemplates();
  await loadCampaigns();
  await loadLeads();
  await loadLogs();
  await loadKeywords();
}

async function refreshDashboard() {
  await refreshAll();
  showNotification('Dashboard data refreshed', 'success');
}

// ----------------- AUTH & STATUS -----------------
async function checkStatus() {
  try {
    const res = await fetch('/api/status');
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
      
      sidebarDot.className = 'w-3 h-3 rounded-full bg-brand-400 pulse-emerald';
      sidebarName.innerText = tg.user.first_name + (tg.user.username ? ` (@${tg.user.username})` : '');
      sidebarSub.innerText = tg.user.phone ? `+${tg.user.phone}` : 'Connected';

      setupDot.className = 'w-3.5 h-3.5 rounded-full bg-brand-400';
      setupTitle.innerText = 'Connected';
      setupDesc.innerText = `Logged in as ${tg.user.first_name} (@${tg.user.username || 'No Handle'})`;
      if (btnLogout) btnLogout.classList.remove('hidden');

      if (tg.api_id) document.getElementById('apiIdInput').value = tg.api_id;
      if (tg.phone) document.getElementById('phoneInput').value = tg.phone;
    } else {
      if (unauthAlert) unauthAlert.classList.remove('hidden');

      sidebarDot.className = 'w-3 h-3 rounded-full bg-amber-500';
      sidebarName.innerText = 'Not Connected';
      sidebarSub.innerText = 'Connect Telegram';

      setupDot.className = 'w-3.5 h-3.5 rounded-full bg-slate-500';
      setupTitle.innerText = 'Disconnected';
      setupDesc.innerText = 'Enter your Telegram credentials below to sign in.';
      if (btnLogout) btnLogout.classList.add('hidden');
    }

    // Live scout button state
    updateLiveScoutUI(data.live_scout_active);

  } catch (err) {
    console.error('Status check failed:', err);
  }
}

async function handleSendCode(e) {
  e.preventDefault();
  const apiId = document.getElementById('apiIdInput').value;
  const apiHash = document.getElementById('apiHashInput').value;
  const phone = document.getElementById('phoneInput').value;

  const btn = document.getElementById('btnRequestCode');
  btn.disabled = true;
  btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin mr-2"></i> Sending OTP...';

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
    btn.disabled = false;
    btn.innerHTML = '<span>Send Login Code to Telegram</span> <i class="fa-solid fa-arrow-right"></i>';
  }
}

async function handleVerifyCode(e) {
  e.preventDefault();
  const code = document.getElementById('otpCodeInput').value;
  const password = document.getElementById('twoFactorPasswordInput').value;
  const btn = document.getElementById('btnSubmitOtp');

  btn.disabled = true;
  btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin mr-2"></i> Verifying...';

  try {
    const res = await fetch('/api/auth/verify-code', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code, password: password || null })
    });
    const data = await res.json();

    if (data.need_2fa) {
      document.getElementById('twoFactorField').classList.remove('hidden');
      showNotification('Your account has Two-Factor Authentication. Please enter your 2FA password.', 'warning');
    } else if (data.success) {
      closeModal('otpModal');
      showNotification(`Successfully logged into Telegram!`, 'success');
      await checkStatus();
      await loadGroups();
    } else {
      showNotification(data.detail || data.error || 'Verification failed', 'error');
    }
  } catch (err) {
    showNotification(err.message, 'error');
  } finally {
    btn.disabled = false;
    btn.innerHTML = 'Confirm & Log In';
  }
}

async function logoutTelegram() {
  if (!confirm('Are you sure you want to log out of Telegram?')) return;
  try {
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

// ----------------- TEMPLATES -----------------
async function loadTemplates() {
  try {
    const res = await fetch('/api/templates');
    state.templates = await res.json();
    renderTemplatesList();
    renderTemplatePickers();
  } catch (err) {
    console.error('Failed to load templates:', err);
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
  const editId = document.getElementById('editTemplateId').value;
  const name = document.getElementById('tplNameInput').value;
  const content = document.getElementById('tplContentInput').value;

  if (!name.trim() || !content.trim()) {
    showNotification('Template name and content are required', 'warning');
    return;
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
      showNotification(`Template ${editId ? 'updated' : 'created'} successfully!`, 'success');
      await loadTemplates();
      await loadStats();
    } else {
      const err = await res.json();
      showNotification(err.detail || 'Failed to save template', 'error');
    }
  } catch (err) {
    showNotification(err.message, 'error');
  }
}

async function deleteTemplateItem(id) {
  if (!confirm('Are you sure you want to delete this template?')) return;
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
      showNotification(`Scout scan complete! Discovered ${data.total_leads_found} new leads.`, 'success');
      await loadLeads();
      await loadStats();
      await loadLogs();
      switchTab('tab-leads');
    } else {
      showNotification(data.error || 'Scout scan failed', 'error');
    }
  } catch (err) {
    showNotification(err.message, 'error');
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<i class="fa-solid fa-crosshairs"></i> Launch Scout Scanner';
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
    const data = await res.json();
    document.getElementById('kpiLeads').innerText = data.leads_count || 0;
    document.getElementById('kpiPosts').innerText = data.posts_sent || 0;
    document.getElementById('kpiTemplates').innerText = data.templates_count || 0;
    document.getElementById('kpiActiveCampaigns').innerText = data.active_campaigns || 0;
  } catch (err) {
    console.error('Failed to load stats:', err);
  }
}

async function loadLogs() {
  try {
    const res = await fetch('/api/logs?limit=50');
    const logs = await res.json();
    const consoleEl = document.getElementById('logsConsole');
    if (!consoleEl) return;

    if (logs.length === 0) {
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
          <span class="text-slate-500 text-[10px] select-none">[${l.timestamp}]</span>
          <span class="text-[10px] px-1.5 rounded font-bold ${colorClass} bg-slate-900 border border-slate-800">[${l.category}]</span>
          <span class="${colorClass}">${escapeHtml(l.message)}</span>
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
