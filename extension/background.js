/**
 * LinkedIn Attention Guardian Background Service Worker
 * Coordinates network fetches and local storage syncing for the stealth architecture.
 */

const API_BASE = "http://127.0.0.1:8000";

// Helper to initialize local storage values on startup
chrome.runtime.onInstalled.addListener(() => {
  chrome.storage.local.set({
    totalProcessed: 0,
    filteredCount: 0,
    hiddenPosts: []
  }, () => {
    console.log("[Guardian Service Worker] Storage initialized.");
  });
});

// Rate-limit safety queue
let curationQueue = [];
let processingQueue = false;

function processNextCuration() {
  if (curationQueue.length === 0) {
    processingQueue = false;
    chrome.storage.local.set({ queueCount: 0 });
    return;
  }

  processingQueue = true;
  chrome.storage.local.set({ queueCount: curationQueue.length });

  const { request, sendResponse } = curationQueue.shift();

  fetch(`${API_BASE}/curate`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(request.postData),
  })
    .then((res) => {
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return res.json();
    })
    .then((data) => {
      chrome.storage.local.get(["totalProcessed", "filteredCount", "hiddenPosts"], (store) => {
        let total = (store.totalProcessed || 0) + 1;
        let filtered = store.filteredCount || 0;
        let list = store.hiddenPosts || [];

        if (data.action === "hide" || data.action === "collapse") {
          filtered += 1;
          
          if (!list.some(p => p.postUrn === data.post_urn)) {
            list.unshift({
              postUrn: data.post_urn,
              authorName: request.postData.author_name,
              authorUrn: request.postData.author_urn,
              postText: request.postData.post_text,
              action: data.action,
              matchedDetector: data.matched_detector,
              explanation: data.explanation,
              timestamp: Date.now()
            });
          }
        }

        chrome.storage.local.set({
          totalProcessed: total,
          filteredCount: filtered,
          hiddenPosts: list.slice(0, 100)
        }, () => {
          sendResponse({ success: true, data });
          // Space requests out by 2000ms to stay within Groq's free limit (30 RPM)
          setTimeout(processNextCuration, 2000);
        });
      });
    })
    .catch((err) => {
      console.error("[Guardian] Curation request failed:", err);
      sendResponse({ success: false, error: err.message });
      setTimeout(processNextCuration, 2000);
    });
}

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  // Safe logging proxy from content script
  if (request.action === "log") {
    console.log(`[Content Script] ${request.message}`, request.data || "");
    sendResponse({ success: true });
    return true;
  }

  if (request.action === "curate") {
    curationQueue.push({ request, sendResponse });
    chrome.storage.local.set({ queueCount: curationQueue.length });
    
    if (!processingQueue) {
      processNextCuration();
    }
    return true; // Keep message channel open for async response
  }

  if (request.action === "restore" || request.action === "correction") {
    const postUrn = request.postUrn || (request.correctionData && request.correctionData.post_urn);
    
    if (!postUrn) {
      sendResponse({ success: false, error: "Missing post URN" });
      return true;
    }

    // 1. Dispatch correction to local backend
    fetch(`${API_BASE}/action/correction`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        post_urn: postUrn,
        action: "restore"
      }),
    })
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then(() => {
        // 2. Remove post from hidden storage list & adjust counter
        chrome.storage.local.get(["filteredCount", "hiddenPosts"], (store) => {
          const list = store.hiddenPosts || [];
          const filtered = Math.max(0, (store.filteredCount || 0) - 1);
          const newList = list.filter(p => p.postUrn !== postUrn);

          chrome.storage.local.set({
            filteredCount: filtered,
            hiddenPosts: newList
          }, () => {
            sendResponse({ success: true });
          });
        });
      })
      .catch((err) => {
        console.error("[Guardian] Correction dispatch failed:", err);
        sendResponse({ success: false, error: err.message });
      });
    return true;
  }
});
