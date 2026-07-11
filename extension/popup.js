document.addEventListener("DOMContentLoaded", () => {
  initTabs();
  loadStats();
  loadFilters();
  loadLogs();
  initQueueListener();
});

// Setup tab switches
function initTabs() {
  const btnFilters = document.getElementById("tab-filters");
  const btnLogs = document.getElementById("tab-logs");
  const contentFilters = document.getElementById("content-filters");
  const contentLogs = document.getElementById("content-logs");

  btnFilters.addEventListener("click", () => {
    btnFilters.classList.add("active");
    btnLogs.classList.remove("active");
    contentFilters.classList.add("active");
    contentLogs.classList.remove("active");
  });

  btnLogs.addEventListener("click", () => {
    btnLogs.classList.add("active");
    btnFilters.classList.remove("active");
    contentLogs.classList.add("active");
    contentFilters.classList.remove("active");
    loadLogs();
  });
}

// Load stats from chrome.storage.local (stealth storage-sync pattern)
function loadStats() {
  chrome.storage.local.get(["totalProcessed", "filteredCount"], (store) => {
    document.getElementById("stat-total").innerText = store.totalProcessed || 0;
    document.getElementById("stat-filtered").innerText = store.filteredCount || 0;
  });
}

// Fetch filter settings from the local backend DB
const API_BASE = "http://127.0.0.1:8000";
async function loadFilters() {
  try {
    const res = await fetch(`${API_BASE}/settings/filters`);
    if (!res.ok) throw new Error("API error");
    const filters = await res.json();

    filters.forEach(filter => {
      const checkbox = document.getElementById(`chk-${filter.detector_id}`);
      if (checkbox) {
        checkbox.checked = filter.enabled;
        
        checkbox.onchange = null; // Unbind duplicate events
        checkbox.addEventListener("change", async () => {
          await updateFilter(filter.detector_id, checkbox.checked);
        });
      }
    });
  } catch (err) {
    console.warn("Could not load filter toggles from local server:", err);
  }
}

// Update filter selection in local backend
async function updateFilter(detectorId, enabled) {
  try {
    const res = await fetch(`${API_BASE}/settings/filters`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        detector_id: detectorId,
        enabled: enabled,
      }),
    });
    if (!res.ok) throw new Error("Failed update");
  } catch (err) {
    console.error("Error updating filter toggles:", err);
    const checkbox = document.getElementById(`chk-${detectorId}`);
    if (checkbox) checkbox.checked = !enabled; // Revert
  }
}

// Load blocked logs from chrome.storage.local
function loadLogs() {
  const container = document.getElementById("logs-container");
  container.innerHTML = `<div style="text-align: center; color: var(--text-muted); font-size: 11px; padding: 20px;">Loading history...</div>`;

  chrome.storage.local.get(["hiddenPosts"], (store) => {
    const logs = store.hiddenPosts || [];

    if (logs.length === 0) {
      container.innerHTML = `<div style="text-align: center; color: var(--text-muted); font-size: 11px; padding: 20px;">No curation actions logged yet.</div>`;
      return;
    }

    container.innerHTML = "";
    logs.forEach(log => {
      const card = document.createElement("div");
      card.className = "log-card";
      card.style.marginBottom = "10px";
      card.style.position = "relative";

      const time = new Date(log.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      const detectorLabel = log.matchedDetector 
        ? log.matchedDetector.toUpperCase().replace("_", " ") 
        : "FILTERED";

      card.innerHTML = `
        <div class="log-header" style="display: flex; justify-content: space-between; align-items: flex-start; gap: 8px;">
          <div style="max-width: 75%;">
            <strong style="color: #ffffff; font-size: 12px;">${escapeHtml(log.authorName || "LinkedIn User")}</strong>
            <div style="font-size: 9px; color: var(--text-muted); margin-top: 2px;">${time} • URN: ${escapeHtml(log.postUrn.substring(0, 15))}</div>
          </div>
          <span class="log-detector" style="white-space: nowrap;">${detectorLabel}</span>
        </div>
        <div class="log-explanation" style="margin-top: 6px; font-style: italic; color: #a5b4fc;">Reason: ${escapeHtml(log.explanation || "Low value")}</div>
        <div class="log-text-box" style="
          margin-top: 6px; 
          font-size: 10px; 
          color: var(--text-muted); 
          line-height: 1.35;
          max-height: 38px;
          overflow: hidden;
          transition: max-height 0.25s ease-out;
        ">"${escapeHtml(log.postText)}"</div>
        <div style="margin-top: 8px; display: flex; justify-content: space-between; align-items: center;">
          <button class="popup-view-btn" style="
            background: none;
            border: none;
            color: #818cf8;
            font-size: 10px;
            font-weight: 600;
            cursor: pointer;
            padding: 0;
            text-decoration: underline;
          ">View Full Post</button>
          
          <button class="popup-restore-btn" data-urn="${log.postUrn}" style="
            background: rgba(99, 102, 241, 0.15);
            border: 1px solid var(--primary);
            color: #a5b4fc;
            padding: 4px 10px;
            border-radius: 4px;
            font-size: 10px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s ease;
          ">Restore Post</button>
        </div>
      `;

      // Bind local view toggle
      const viewBtn = card.querySelector(".popup-view-btn");
      const textBox = card.querySelector(".log-text-box");
      viewBtn.addEventListener("click", () => {
        if (textBox.style.maxHeight === "38px") {
          textBox.style.maxHeight = "500px";
          viewBtn.innerText = "Collapse Text";
        } else {
          textBox.style.maxHeight = "38px";
          viewBtn.innerText = "View Full Post";
        }
      });

      // Bind restore action
      const restoreBtn = card.querySelector(".popup-restore-btn");
      restoreBtn.addEventListener("click", () => {
        restoreBtn.innerText = "Restoring...";
        restoreBtn.disabled = true;
        restorePostInFeed(log.postUrn, card);
      });

      container.appendChild(card);
    });
  });
}

// Dispatch restore instructions back to content script and sync SQLite backend
function restorePostInFeed(postUrn, cardElement) {
  // 1. Query the active tab to tell content script to un-hide the post
  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    if (tabs.length === 0) {
      alert("Please keep your LinkedIn tab active to restore posts.");
      loadLogs();
      return;
    }

    chrome.tabs.sendMessage(tabs[0].id, { action: "restore_post", postUrn: postUrn }, (response) => {
      if (chrome.runtime.lastError || !response || !response.success) {
        console.warn("[Guardian] Content script restore failed or tab reloaded:", chrome.runtime.lastError);
        alert("Could not restore post. Make sure LinkedIn is open and active.");
        loadLogs();
        return;
      }

      // 2. Local DOM restore succeeded. Tell background to sync storage and notify FastAPI backend
      chrome.runtime.sendMessage({ action: "restore", postUrn: postUrn }, (bgResponse) => {
        cardElement.remove();
        loadStats(); // Reload header stats counter
        loadLogs();  // Refresh logs tab
      });
    });
  });
}

function escapeHtml(str) {
  if (!str) return "";
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function initQueueListener() {
  const queueDiv = document.getElementById("queue-status");
  const queueText = document.getElementById("queue-text");

  function updateQueueUI(count) {
    if (count > 0) {
      queueDiv.style.display = "flex";
      queueText.innerText = `Curation Queue: ${count} post${count > 1 ? 's' : ''} remaining...`;
    } else {
      queueDiv.style.display = "none";
    }
  }

  // Initial check
  chrome.storage.local.get(["queueCount"], (store) => {
    updateQueueUI(store.queueCount || 0);
  });

  // Listen for background updates
  chrome.storage.onChanged.addListener((changes) => {
    if (changes.queueCount) {
      updateQueueUI(changes.queueCount.newValue || 0);
    }
  });
}
