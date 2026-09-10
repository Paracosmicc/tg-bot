/**
 * Vaidehi Bot — Web Control Panel Client Logic
 */

const DEFAULT_API_URL = "https://tg-bot-9ulh.onrender.com";

let API_URL = localStorage.getItem("vaidehi_api_url") || DEFAULT_API_URL;
let AUTH_TOKEN = localStorage.getItem("vaidehi_auth_token") || "";

let loadedUsers = [];
let currentUserFilter = "all";
let userSearchQuery = "";

let loadedPhotos = [];
let currentPhotoFilter = "all";

// DOM Elements
const loginModal = document.getElementById("login-modal");
const loginForm = document.getElementById("login-form");
const passwordInput = document.getElementById("password-input");
const apiUrlInput = document.getElementById("api-url-input");
const loginError = document.getElementById("login-error");
const logoutBtn = document.getElementById("logout-btn");
const refreshBtn = document.getElementById("refresh-btn");

const settingsModal = document.getElementById("settings-modal");
const settingsBtn = document.getElementById("settings-btn");
const closeSettingsBtn = document.getElementById("close-settings-btn");
const settingApiUrl = document.getElementById("setting-api-url");
const saveSettingsBtn = document.getElementById("save-settings-btn");

// Init
document.addEventListener("DOMContentLoaded", () => {
  if (window.lucide) {
    window.lucide.createIcons();
  }

  apiUrlInput.value = API_URL;
  settingApiUrl.value = API_URL;

  if (AUTH_TOKEN) {
    testAuthAndLoad();
  } else {
    showLoginModal();
  }

  setupEventListeners();
  setupBroadcastPreview();
  setupDropzones();
});

// API Helper
async function apiFetch(endpoint, options = {}) {
  const headers = options.headers || {};
  if (AUTH_TOKEN) {
    headers["Authorization"] = `Bearer ${AUTH_TOKEN}`;
  }

  const cleanUrl = `${API_URL.replace(/\/+$/, "")}${endpoint}`;

  try {
    const res = await fetch(cleanUrl, {
      ...options,
      headers,
    });

    if (res.status === 401) {
      localStorage.removeItem("vaidehi_auth_token");
      AUTH_TOKEN = "";
      showLoginModal("Session expired. Please log in again.");
      throw new Error("Unauthorized");
    }

    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || "API request failed");
    }
    return data;
  } catch (err) {
    console.error(`API error on ${endpoint}:`, err);
    throw err;
  }
}

// Authentication
async function testAuthAndLoad() {
  try {
    await fetchStats();
    hideLoginModal();
    loadAllData();
  } catch (err) {
    showLoginModal("Authentication failed. Please verify your password.");
  }
}

function showLoginModal(error = "") {
  loginModal.classList.add("active");
  if (error) {
    loginError.textContent = error;
    loginError.classList.remove("hidden");
  } else {
    loginError.classList.add("hidden");
  }
}

function hideLoginModal() {
  loginModal.classList.remove("active");
  loginError.classList.add("hidden");
}

// Event Listeners
function setupEventListeners() {
  // Login Form Submit
  loginForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const enteredPassword = passwordInput.value.trim();
    const enteredApiUrl = apiUrlInput.value.trim() || DEFAULT_API_URL;

    API_URL = enteredApiUrl;
    localStorage.setItem("vaidehi_api_url", API_URL);

    const loginBtn = document.getElementById("login-btn");
    loginBtn.disabled = true;
    loginBtn.querySelector("span").textContent = "Authenticating...";

    try {
      const res = await fetch(`${API_URL.replace(/\/+$/, "")}/api/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password: enteredPassword }),
      });

      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Invalid password");

      AUTH_TOKEN = data.token;
      localStorage.setItem("vaidehi_auth_token", AUTH_TOKEN);

      hideLoginModal();
      loadAllData();
    } catch (err) {
      showLoginModal(err.message || "Failed to connect to backend");
    } finally {
      loginBtn.disabled = false;
      loginBtn.querySelector("span").textContent = "Authenticate";
    }
  });

  // Logout
  logoutBtn.addEventListener("click", () => {
    localStorage.removeItem("vaidehi_auth_token");
    AUTH_TOKEN = "";
    showLoginModal("You have been logged out.");
  });

  // Refresh
  refreshBtn.addEventListener("click", () => {
    refreshBtn.classList.add("spin");
    loadAllData().finally(() => {
      setTimeout(() => refreshBtn.classList.remove("spin"), 500);
    });
  });

  // Settings Modal
  settingsBtn.addEventListener("click", () => {
    settingApiUrl.value = API_URL;
    settingsModal.classList.add("active");
  });

  closeSettingsBtn.addEventListener("click", () => {
    settingsModal.classList.remove("active");
  });

  saveSettingsBtn.addEventListener("click", () => {
    API_URL = settingApiUrl.value.trim() || DEFAULT_API_URL;
    localStorage.setItem("vaidehi_api_url", API_URL);
    settingsModal.classList.remove("active");
    loadAllData();
  });

  // Tabs Navigation
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
      document.querySelectorAll(".tab-content").forEach((c) => c.classList.remove("active"));

      btn.classList.add("active");
      const tabId = btn.getAttribute("data-tab");
      const targetContent = document.getElementById(`tab-${tabId}`);
      if (targetContent) targetContent.classList.add("active");
    });
  });

  // Broadcast Form Submit
  const broadcastForm = document.getElementById("broadcast-form");
  broadcastForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const msg = document.getElementById("broadcast-msg").value.trim();
    const target = document.querySelector('input[name="broadcast-target"]:checked').value;
    const pin = document.getElementById("broadcast-pin").checked;
    const statusBox = document.getElementById("broadcast-status-box");
    const sendBtn = document.getElementById("send-broadcast-btn");

    if (!msg) return;

    if (!confirm(`Are you sure you want to broadcast this message to "${target.toUpperCase()}"?`)) {
      return;
    }

    sendBtn.disabled = true;
    sendBtn.querySelector("span").textContent = "Broadcasting...";

    try {
      const res = await apiFetch("/api/broadcast", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: msg, target, pin }),
      });

      statusBox.className = "alert alert-info mt-3";
      statusBox.innerHTML = `🚀 <strong>Broadcast Launched!</strong> ${res.message}`;
      statusBox.classList.remove("hidden");
      document.getElementById("broadcast-msg").value = "";
      updateLivePreview("");
    } catch (err) {
      statusBox.className = "alert alert-danger mt-3";
      statusBox.textContent = `❌ Error: ${err.message}`;
      statusBox.classList.remove("hidden");
    } finally {
      sendBtn.disabled = false;
      sendBtn.querySelector("span").textContent = "Launch Broadcast";
    }
  });

  // Direct Send Form Submit
  const directForm = document.getElementById("direct-send-form");
  const directGroupSelect = document.getElementById("direct-group-select");
  const directChatId = document.getElementById("direct-chat-id");

  directGroupSelect.addEventListener("change", () => {
    if (directGroupSelect.value) {
      directChatId.value = directGroupSelect.value;
    }
  });

  directForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const chatId = parseInt(directChatId.value);
    const message = document.getElementById("direct-message").value.trim();
    const pin = document.getElementById("direct-pin").checked;
    const statusBox = document.getElementById("direct-status-box");
    const sendBtn = document.getElementById("direct-send-btn");

    if (!chatId || !message) return;

    sendBtn.disabled = true;
    sendBtn.querySelector("span").textContent = "Sending...";

    try {
      await apiFetch("/api/send", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ chat_id: chatId, message, pin }),
      });

      statusBox.className = "alert alert-info mt-3";
      statusBox.innerHTML = `✅ Message successfully sent to <code>${chatId}</code>!`;
      statusBox.classList.remove("hidden");
      document.getElementById("direct-message").value = "";
    } catch (err) {
      statusBox.className = "alert alert-danger mt-3";
      statusBox.textContent = `❌ Error: ${err.message}`;
      statusBox.classList.remove("hidden");
    } finally {
      sendBtn.disabled = false;
      sendBtn.querySelector("span").textContent = "Send Message Now";
    }
  });

  // Quick VIP Form Submit
  const quickVipForm = document.getElementById("quick-vip-form");
  if (quickVipForm) {
    quickVipForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const userIdInput = document.getElementById("vip-user-id-input");
      const durationSelect = document.getElementById("vip-duration-select");
      const statusBox = document.getElementById("quick-vip-status");
      const grantBtn = document.getElementById("grant-vip-btn");

      const userId = parseInt(userIdInput.value.trim());
      const durationDays = parseInt(durationSelect.value);

      if (!userId) return;

      grantBtn.disabled = true;
      grantBtn.querySelector("span").textContent = "Activating VIP...";

      try {
        const res = await apiFetch("/api/users/vip", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            user_id: userId,
            duration_days: durationDays > 0 ? durationDays : null,
            action: "grant",
          }),
        });

        statusBox.className = "alert alert-info mt-3";
        statusBox.innerHTML = `👑 <strong>Success!</strong> ${res.message}`;
        statusBox.classList.remove("hidden");
        userIdInput.value = "";

        // Refresh stats and users
        fetchUsers();
        fetchStats();
      } catch (err) {
        statusBox.className = "alert alert-danger mt-3";
        statusBox.textContent = `❌ Error: ${err.message}`;
        statusBox.classList.remove("hidden");
      } finally {
        grantBtn.disabled = false;
        grantBtn.querySelector("span").textContent = "Grant VIP Status";
      }
    });
  }

  // User Search Input
  const userSearchInput = document.getElementById("user-search-input");
  if (userSearchInput) {
    userSearchInput.addEventListener("input", (e) => {
      userSearchQuery = e.target.value.trim().toLowerCase();
      renderUsersTable();
    });
  }

  // Photo Filter Pills (All, Standard, VIP)
  document.querySelectorAll("[data-photo-filter]").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll("[data-photo-filter]").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      currentPhotoFilter = btn.getAttribute("data-photo-filter") || "all";
      renderPhotosGrid();
    });
  });

  // User Filter Pills (All, VIP Only, Free Only)
  document.querySelectorAll("[data-filter]").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll("[data-filter]").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      currentUserFilter = btn.getAttribute("data-filter") || "all";
      renderUsersTable();
    });
  });
}

// Load All Data
async function loadAllData() {
  await Promise.allSettled([
    fetchStats(),
    fetchGroups(),
    fetchPhotos(),
    fetchVoices(),
    fetchUsers(),
  ]);
  if (window.lucide) window.lucide.createIcons();
}

// Fetch Stats
async function fetchStats() {
  const data = await apiFetch("/api/stats");

  // Top Nav pills
  document.getElementById("stat-model").textContent = data.model || "--";
  document.getElementById("stat-uptime").textContent = data.uptime || "--";
  document.getElementById("stat-redis-hit").textContent = data.cache?.hit_rate || "--";

  // KPIs
  document.getElementById("kpi-messages").textContent = (data.counts?.messages || 0).toLocaleString();
  document.getElementById("kpi-users").textContent = (data.counts?.users || 0).toLocaleString();
  document.getElementById("kpi-groups").textContent = (data.counts?.groups || 0).toLocaleString();
  document.getElementById("kpi-couples").textContent = (data.counts?.active_couples || 0).toLocaleString();

  // Health Card
  document.getElementById("health-api-url").textContent = API_URL;
  document.getElementById("health-model").textContent = data.model || "--";
  document.getElementById("health-redis-hits").textContent = `${data.cache?.hits || 0} / ${data.cache?.total || 0}`;
  document.getElementById("health-redis-rate").textContent = data.cache?.hit_rate || "--";
  if (document.getElementById("health-premium-cnt")) {
    document.getElementById("health-premium-cnt").textContent = (data.counts?.premium_users || 0).toLocaleString();
  }
  document.getElementById("health-photos-cnt").textContent = data.media?.photos || 0;
  document.getElementById("health-voices-cnt").textContent = data.media?.voices || 0;

  // Tabs badge
  document.getElementById("tab-photo-cnt").textContent = data.media?.photos || 0;
  document.getElementById("tab-voice-cnt").textContent = data.media?.voices || 0;
}

// Fetch Groups
async function fetchGroups() {
  const data = await apiFetch("/api/groups");
  const tbody = document.getElementById("groups-table-body");
  const directSelect = document.getElementById("direct-group-select");
  const badge = document.getElementById("groups-count-badge");

  const groups = data.groups || [];
  badge.textContent = `${groups.length} Groups`;

  if (groups.length === 0) {
    tbody.innerHTML = `<tr><td colspan="3" class="text-center py-4 text-muted">No registered groups found in database yet.</td></tr>`;
    directSelect.innerHTML = `<option value="">-- No Groups Available --</option>`;
    return;
  }

  tbody.innerHTML = groups
    .map(
      (g) => `
      <tr>
        <td><strong>${escapeHtml(g.title)}</strong></td>
        <td><code>${g.chat_id}</code></td>
        <td>
          <button class="btn btn-secondary btn-sm" onclick="quickSelectGroup(${g.chat_id})">
            💬 Message
          </button>
        </td>
      </tr>
    `
    )
    .join("");

  directSelect.innerHTML =
    `<option value="">-- Select from Registered Groups --</option>` +
    groups.map((g) => `<option value="${g.chat_id}">${escapeHtml(g.title)} (${g.chat_id})</option>`).join("");
}

window.quickSelectGroup = function (chatId) {
  const messengerTab = document.querySelector('.tab-btn[data-tab="messenger"]');
  if (messengerTab) messengerTab.click();
  document.getElementById("direct-chat-id").value = chatId;
  document.getElementById("direct-message").focus();
};

// Photos Management
async function fetchPhotos() {
  const data = await apiFetch("/api/media/photos?type=all");
  loadedPhotos = data.photos || [];

  // Update counters
  const totalCount = loadedPhotos.length;
  const standardCount = loadedPhotos.filter((p) => !p.is_vip).length;
  const vipCount = loadedPhotos.filter((p) => p.is_vip).length;

  if (document.getElementById("count-all-photos")) {
    document.getElementById("count-all-photos").textContent = totalCount;
  }
  if (document.getElementById("count-standard-photos")) {
    document.getElementById("count-standard-photos").textContent = standardCount;
  }
  if (document.getElementById("count-vip-photos")) {
    document.getElementById("count-vip-photos").textContent = vipCount;
  }

  renderPhotosGrid();
}

function renderPhotosGrid() {
  const grid = document.getElementById("photos-grid");
  if (!grid) return;

  let filtered = loadedPhotos;
  if (currentPhotoFilter === "standard") {
    filtered = loadedPhotos.filter((p) => !p.is_vip);
  } else if (currentPhotoFilter === "vip") {
    filtered = loadedPhotos.filter((p) => p.is_vip);
  }

  if (filtered.length === 0) {
    grid.innerHTML = `<div class="text-center py-5 text-muted col-span-full">No photo assets found for current filter. Upload photos above!</div>`;
    return;
  }

  grid.innerHTML = filtered
    .map(
      (p) => `
      <div class="photo-card ${p.is_vip ? "photo-card-vip" : ""}">
        <div class="photo-badge-wrapper">
          <span class="badge ${p.is_vip ? "badge-purple" : "badge-secondary"}">
            ${p.is_vip ? "👑 VIP Photo (/vippic)" : "🌸 Standard (/pic)"}
          </span>
        </div>
        <img src="${p.url}" alt="${p.filename}" class="photo-thumb" loading="lazy">
        <div class="photo-footer">
          <span class="photo-name" title="${p.filename}">${p.filename}</span>
          <span class="text-muted text-xs">${p.size_kb} KB</span>
          <button class="btn-delete-photo" onclick="deletePhoto('${p.filename}', ${p.is_vip ? "true" : "false"})" title="Delete Photo">
            🗑️
          </button>
        </div>
      </div>
    `
    )
    .join("");
}

window.deletePhoto = async function (filename, isVip = false) {
  if (!confirm(`Delete photo "${filename}" (${isVip ? "VIP" : "Standard"})?`)) return;
  try {
    await apiFetch(`/api/media/photos/${encodeURIComponent(filename)}?is_vip=${isVip}`, { method: "DELETE" });
    fetchPhotos();
    fetchStats();
  } catch (err) {
    alert(`Failed to delete: ${err.message}`);
  }
};

// Voice Notes Management
async function fetchVoices() {
  const data = await apiFetch("/api/media/voices");
  const list = document.getElementById("voices-list");
  const voices = data.voices || [];

  if (voices.length === 0) {
    list.innerHTML = `<div class="text-center py-5 text-muted">No voice assets found. Upload audio files above!</div>`;
    return;
  }

  list.innerHTML = voices
    .map(
      (v) => `
      <div class="voice-item">
        <div class="voice-item-left">
          <div class="voice-icon"><i data-lucide="volume-2"></i></div>
          <div class="voice-info">
            <span class="voice-filename">${v.filename}</span>
            <span class="voice-intent-badge">🎯 ${v.intent}</span>
          </div>
        </div>
        <audio controls class="voice-audio-player" src="${v.url}" preload="none"></audio>
        <button class="btn btn-danger-outline btn-sm" onclick="deleteVoice('${v.filename}')" title="Delete Voice">
          🗑️ Delete
        </button>
      </div>
    `
    )
    .join("");

  if (window.lucide) window.lucide.createIcons();
}

window.deleteVoice = async function (filename) {
  if (!confirm(`Delete voice note "${filename}"?`)) return;
  try {
    await apiFetch(`/api/media/voices/${encodeURIComponent(filename)}`, { method: "DELETE" });
    fetchVoices();
    fetchStats();
  } catch (err) {
    alert(`Failed to delete: ${err.message}`);
  }
};

// Dropzone & File Uploads
function setupDropzones() {
  // Standard Photo Upload
  const photoDrop = document.getElementById("photo-dropzone");
  const photoInput = document.getElementById("photo-upload-input");
  if (photoDrop && photoInput) {
    photoDrop.addEventListener("click", () => photoInput.click());
    photoInput.addEventListener("change", () => handleUpload(photoInput.files[0], "/api/media/photos/upload?is_vip=false", fetchPhotos));

    photoDrop.addEventListener("dragover", (e) => { e.preventDefault(); photoDrop.classList.add("dragover"); });
    photoDrop.addEventListener("dragleave", () => photoDrop.classList.remove("dragover"));
    photoDrop.addEventListener("drop", (e) => {
      e.preventDefault();
      photoDrop.classList.remove("dragover");
      if (e.dataTransfer.files.length) {
        handleUpload(e.dataTransfer.files[0], "/api/media/photos/upload?is_vip=false", fetchPhotos);
      }
    });
  }

  // VIP Photo Upload Button
  const vipPhotoInput = document.getElementById("vip-photo-upload-input");
  if (vipPhotoInput) {
    vipPhotoInput.addEventListener("change", () => handleUpload(vipPhotoInput.files[0], "/api/media/photos/upload?is_vip=true", fetchPhotos));
  }

  // Voice Dropzone
  const voiceDrop = document.getElementById("voice-dropzone");
  const voiceInput = document.getElementById("voice-upload-input");
  if (voiceDrop && voiceInput) {
    voiceDrop.addEventListener("click", () => voiceInput.click());
    voiceInput.addEventListener("change", () => handleUpload(voiceInput.files[0], "/api/media/voices/upload", fetchVoices));

    voiceDrop.addEventListener("dragover", (e) => { e.preventDefault(); voiceDrop.classList.add("dragover"); });
    voiceDrop.addEventListener("dragleave", () => voiceDrop.classList.remove("dragover"));
    voiceDrop.addEventListener("drop", (e) => {
      e.preventDefault();
      voiceDrop.classList.remove("dragover");
      if (e.dataTransfer.files.length) {
        handleUpload(e.dataTransfer.files[0], "/api/media/voices/upload", fetchVoices);
      }
    });
  }
}

async function handleUpload(file, endpoint, callback) {
  if (!file) return;
  const formData = new FormData();
  formData.append("file", file);

  try {
    const res = await fetch(`${API_URL.replace(/\/+$/, "")}${endpoint}`, {
      method: "POST",
      headers: { Authorization: `Bearer ${AUTH_TOKEN}` },
      body: formData,
    });

    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Upload failed");

    callback();
    fetchStats();
  } catch (err) {
    alert(`Upload Error: ${err.message}`);
  }
}

// Live Telegram Markdown Preview
function setupBroadcastPreview() {
  const textarea = document.getElementById("broadcast-msg");
  const charCounter = document.getElementById("char-counter");

  textarea.addEventListener("input", () => {
    const text = textarea.value;
    charCounter.textContent = `${text.length} chars`;
    updateLivePreview(text);
  });
}

function updateLivePreview(rawText) {
  const preview = document.getElementById("tg-preview-text");
  if (!rawText.trim()) {
    preview.innerHTML = `<span class="text-muted">Type in the composer to see the live Telegram message preview here...</span>`;
    return;
  }

  // Simple Markdown Converter for Telegram style
  let formatted = escapeHtml(rawText);
  // Bold *text*
  formatted = formatted.replace(/\*(.*?)\*/g, "<strong>$1</strong>");
  // Italic _text_
  formatted = formatted.replace(/_(.*?)_/g, "<em>$1</em>");
  // Inline Code `code`
  formatted = formatted.replace(/`(.*?)`/g, "<code>$1</code>");
  // Newlines
  formatted = formatted.replace(/\n/g, "<br>");

  preview.innerHTML = formatted;
}

function escapeHtml(str) {
  return (str || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

// --------------------------------------------------------------------------
// USERS & VIP MANAGEMENT LOGIC
// --------------------------------------------------------------------------

async function fetchUsers() {
  const tbody = document.getElementById("users-table-body");
  try {
    const data = await apiFetch("/api/users");
    loadedUsers = data.users || [];

    const totalUsers = data.total_users || loadedUsers.length;
    const vipCount = data.vip_count || loadedUsers.filter((u) => u.is_premium).length;
    const freeCount = Math.max(0, totalUsers - vipCount);

    // Update Pills & Tab Badge
    const tabUsersCnt = document.getElementById("tab-users-cnt");
    if (tabUsersCnt) tabUsersCnt.textContent = totalUsers;

    const totalPill = document.getElementById("total-users-pill");
    if (totalPill) totalPill.textContent = `Total: ${totalUsers}`;

    const vipPill = document.getElementById("vip-users-pill");
    if (vipPill) vipPill.textContent = `👑 VIP: ${vipCount}`;

    const freePill = document.getElementById("free-users-pill");
    if (freePill) freePill.textContent = `Free: ${freeCount}`;

    renderUsersTable();
  } catch (err) {
    if (tbody) {
      tbody.innerHTML = `<tr><td colspan="5" class="text-center py-4 text-danger">⚠️ Failed to load users: ${err.message}</td></tr>`;
    }
  }
}

function renderUsersTable() {
  const tbody = document.getElementById("users-table-body");
  if (!tbody) return;

  let filtered = loadedUsers.filter((u) => {
    // Status Filter
    if (currentUserFilter === "vip" && !u.is_premium) return false;
    if (currentUserFilter === "free" && u.is_premium) return false;

    // Search Query
    if (userSearchQuery) {
      const matchName = (u.display_name || "").toLowerCase().includes(userSearchQuery);
      const matchUsername = (u.username || "").toLowerCase().includes(userSearchQuery);
      const matchId = String(u.user_id || "").includes(userSearchQuery);
      return matchName || matchUsername || matchId;
    }
    return true;
  });

  if (filtered.length === 0) {
    tbody.innerHTML = `<tr><td colspan="5" class="text-center py-5 text-muted">No users found matching your criteria.</td></tr>`;
    return;
  }

  tbody.innerHTML = filtered
    .map((u) => {
      const isVip = !!u.is_premium;
      const initial = (u.display_name || u.first_name || "U").trim().charAt(0).toUpperCase();
      const usernameText = u.username ? `@${u.username.replace(/^@/, "")}` : "No username";

      let statusBadge = "";
      if (isVip) {
        let expiryStr = "Lifetime VIP 👑";
        if (u.premium_expires_at) {
          const expDate = new Date(u.premium_expires_at);
          const daysLeft = Math.ceil((expDate - new Date()) / (1000 * 60 * 60 * 24));
          if (daysLeft > 0) {
            expiryStr = `👑 VIP (${daysLeft}d left)`;
          } else {
            expiryStr = `👑 VIP (Expiring)`;
          }
        }
        statusBadge = `<span class="badge-vip" title="${u.premium_expires_at || 'Permanent'}">✨ ${expiryStr}</span>`;
      } else {
        statusBadge = `<span class="badge-free">Free User</span>`;
      }

      return `
        <tr>
          <td>
            <div class="user-cell">
              <div class="user-avatar-initial ${isVip ? "is-vip" : ""}">${escapeHtml(initial)}</div>
              <div class="user-info-text">
                <span class="user-name">${escapeHtml(u.display_name || "Anonymous User")}</span>
                <span class="user-username">${escapeHtml(usernameText)}</span>
              </div>
            </div>
          </td>
          <td>
            <code>${u.user_id}</code>
            <button class="btn btn-icon btn-sm" onclick="copyUserId(${u.user_id})" title="Copy User ID" style="padding: 2px 6px; font-size: 11px; margin-left: 4px;">
              📋
            </button>
          </td>
          <td>
            <span class="badge badge-secondary">${escapeHtml(u.persona_mode || "flirty")}</span>
          </td>
          <td>${statusBadge}</td>
          <td>
            <div class="user-actions">
              ${
                isVip
                  ? `<button class="btn-vip-action btn-vip-revoke" onclick="revokeVipForUser(${u.user_id})" title="Revoke VIP Status">
                      ❌ Revoke VIP
                    </button>`
                  : `<button class="btn-vip-action btn-vip-grant" onclick="quickGrantVipForUser(${u.user_id})" title="Make VIP (30 Days)">
                      👑 Make VIP
                    </button>`
              }
              <button class="btn btn-secondary btn-sm" onclick="quickSelectUserDM(${u.user_id})" title="Send Direct Message">
                💬 DM
              </button>
            </div>
          </td>
        </tr>
      `;
    })
    .join("");
}

window.quickGrantVipForUser = async function (userId) {
  const daysStr = prompt(`Grant VIP status to user ${userId}.\nEnter duration in days (or leave blank for 30 days):`, "30");
  if (daysStr === null) return; // Cancelled

  let days = parseInt(daysStr);
  if (isNaN(days) || days <= 0) {
    days = 30;
  }

  try {
    const res = await apiFetch("/api/users/vip", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        user_id: userId,
        duration_days: days,
        action: "grant",
      }),
    });

    alert(`👑 Success! User ${userId} is now VIP for ${days} days.`);
    fetchUsers();
    fetchStats();
  } catch (err) {
    alert(`❌ Failed to grant VIP: ${err.message}`);
  }
};

window.revokeVipForUser = async function (userId) {
  if (!confirm(`Are you sure you want to REVOKE VIP status from user ${userId}?`)) return;

  try {
    const res = await apiFetch("/api/users/vip", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        user_id: userId,
        action: "revoke",
      }),
    });

    alert(`❌ VIP status revoked for user ${userId}.`);
    fetchUsers();
    fetchStats();
  } catch (err) {
    alert(`❌ Failed to revoke VIP: ${err.message}`);
  }
};

window.quickSelectUserDM = function (userId) {
  const messengerTab = document.querySelector('.tab-btn[data-tab="messenger"]');
  if (messengerTab) messengerTab.click();
  const directChatId = document.getElementById("direct-chat-id");
  if (directChatId) directChatId.value = userId;
  const directMsg = document.getElementById("direct-message");
  if (directMsg) directMsg.focus();
};

window.copyUserId = function (userId) {
  navigator.clipboard.writeText(String(userId)).then(() => {
    alert(`Copied User ID ${userId} to clipboard!`);
  }).catch(() => {
    prompt("User ID:", userId);
  });
};
