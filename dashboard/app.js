/**
 * Vaidehi Bot — Web Control Panel Client Logic
 */

const DEFAULT_API_URL = "https://tg-bot-9ulh.onrender.com";

let API_URL = localStorage.getItem("vaidehi_api_url") || DEFAULT_API_URL;
let AUTH_TOKEN = localStorage.getItem("vaidehi_auth_token") || "";

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
}

// Load All Data
async function loadAllData() {
  await Promise.allSettled([
    fetchStats(),
    fetchGroups(),
    fetchPhotos(),
    fetchVoices(),
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
  const data = await apiFetch("/api/media/photos");
  const grid = document.getElementById("photos-grid");
  const photos = data.photos || [];

  if (photos.length === 0) {
    grid.innerHTML = `<div class="text-center py-5 text-muted col-span-full">No photo assets found. Upload photos above for /pic command!</div>`;
    return;
  }

  grid.innerHTML = photos
    .map(
      (p) => `
      <div class="photo-card">
        <img src="${p.url}" alt="${p.filename}" class="photo-thumb" loading="lazy">
        <div class="photo-footer">
          <span class="photo-name" title="${p.filename}">${p.filename}</span>
          <span class="text-muted text-xs">${p.size_kb} KB</span>
          <button class="btn-delete-photo" onclick="deletePhoto('${p.filename}')" title="Delete Photo">
            🗑️
          </button>
        </div>
      </div>
    `
    )
    .join("");
}

window.deletePhoto = async function (filename) {
  if (!confirm(`Delete photo "${filename}"?`)) return;
  try {
    await apiFetch(`/api/media/photos/${encodeURIComponent(filename)}`, { method: "DELETE" });
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
  // Photo Dropzone
  const photoDrop = document.getElementById("photo-dropzone");
  const photoInput = document.getElementById("photo-upload-input");

  photoDrop.addEventListener("click", () => photoInput.click());
  photoInput.addEventListener("change", () => handleUpload(photoInput.files[0], "/api/media/photos/upload", fetchPhotos));

  photoDrop.addEventListener("dragover", (e) => { e.preventDefault(); photoDrop.classList.add("dragover"); });
  photoDrop.addEventListener("dragleave", () => photoDrop.classList.remove("dragover"));
  photoDrop.addEventListener("drop", (e) => {
    e.preventDefault();
    photoDrop.classList.remove("dragover");
    if (e.dataTransfer.files.length) {
      handleUpload(e.dataTransfer.files[0], "/api/media/photos/upload", fetchPhotos);
    }
  });

  // Voice Dropzone
  const voiceDrop = document.getElementById("voice-dropzone");
  const voiceInput = document.getElementById("voice-upload-input");

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
