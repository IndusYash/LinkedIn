/**
 * LinkedIn Attention Guardian Content Script
 * Refined Stealth Version 3 - Class-obfuscation immune structural card locator,
 * WeakSet in-memory processing registry, and inline-styling visual masks.
 */

(function() {
  // Only execute in the top-most main window context
  if (window.top !== window) {
    return;
  }

  // In-memory set to track observed and processed nodes without modifying DOM attributes
  const observedNodes = new WeakSet();
  const processedPosts = new WeakSet();
  const fallbackPostMap = new Map();

  // Initialize
  function init() {
    safeLog("Invisible content observer active.");
    
    runDiagnostics("Immediate");
    setTimeout(() => {
      runDiagnostics("Delayed 5s");
    }, 5000);

    setupFeedObserver();
    setupMessageListener();
  }

  function runDiagnostics(label) {
    try {
      const url = window.location.href;
      const title = document.title;
      const bodyLength = document.body ? document.body.innerHTML.length : -1;
      const all = document.querySelectorAll("*");
      
      safeLog(`[Diagnostic - ${label}] URL: "${url}", Title: "${title}", DOM elements: ${all.length}, bodyHTML length: ${bodyLength}`);
      
      const classNames = [];
      const dataAttributes = [];
      
      all.forEach((el) => {
        const className = el.className;
        if (typeof className === "string" && className.length > 0) {
          const classes = className.split(' ').filter(x => x.trim());
          classes.forEach(c => {
            if (classNames.length < 20 && !classNames.includes(c)) {
              classNames.push(c);
            }
          });
        }
        
        for (let i = 0; i < el.attributes.length; i++) {
          const attr = el.attributes[i].name;
          if (attr.startsWith("data-") && dataAttributes.length < 20) {
            if (!dataAttributes.some(x => x.name === attr)) {
              dataAttributes.push({ name: attr, tag: el.tagName.toLowerCase(), value: el.attributes[i].value.substring(0, 50) });
            }
          }
        }
      });
      
      safeLog(`[Diagnostic - ${label}] Sample Class Names: ` + JSON.stringify(classNames));
      safeLog(`[Diagnostic - ${label}] Sample Data Attributes: ` + JSON.stringify(dataAttributes));

      // Locate commentary element and trace parent tree layout
      const comm = document.querySelector('[data-sdui-anchor-id^="commentary-"]');
      if (comm) {
        safeLog("[Diagnostic - Tree] Found commentary element. Climbing ancestors...");
        const path = [];
        let el = comm;
        while (el && el !== document.documentElement) {
          const attrs = {};
          for (let i = 0; i < el.attributes.length; i++) {
            attrs[el.attributes[i].name] = el.attributes[i].value;
          }
          path.push({
            tag: el.tagName.toLowerCase(),
            class: el.className,
            attributes: attrs
          });
          el = el.parentElement;
        }
        safeLog("[Diagnostic - Tree] Ancestor Chain: " + JSON.stringify(path));
      } else {
        safeLog("[Diagnostic - Tree] Commentary element not found yet.");
      }
    } catch (e) {
      safeLog(`[Diagnostic - ${label}] Failed: ` + e.message);
    }
  }

  // Resolve the outermost card container to prevent nested matching
  function resolvePostCards() {
    const rawNodes = document.querySelectorAll(
      '[role="listitem"], ' +
      '[data-urn*="urn:li:activity:"], ' +
      '.feed-shared-update-v2, ' +
      'article.update-components-article'
    );
    
    const cards = [];
    rawNodes.forEach((node) => {
      let card = node;
      let parent = card.parentElement;
      while (parent && parent !== document.body) {
        if (
          parent.getAttribute("role") === "listitem" || 
          (parent.getAttribute("data-urn") && parent.getAttribute("data-urn").includes("urn:li:activity:")) ||
          parent.classList.contains("feed-shared-update-v2") ||
          parent.tagName.toLowerCase() === "article"
        ) {
          card = parent;
        }
        parent = parent.parentElement;
      }
      
      if (card && !cards.includes(card)) {
        cards.push(card);
      }
    });
    
    return cards;
  }

  // Scan all matching nodes and register top-level cards with the IntersectionObserver
  function scanAndRegister(io) {
    try {
      const cards = resolvePostCards();
      cards.forEach((card) => {
        if (card && !observedNodes.has(card)) {
          observedNodes.add(card);
          io.observe(card);
        }
      });
    } catch (e) {
      safeLog("Error during scan and register: " + e.message);
    }
  }

  // Setup Curation Engine (Debounced MutationObserver + IntersectionObserver fallback)
  function setupFeedObserver() {
    const observerOptions = {
      root: null,
      rootMargin: "100px", // Pre-fetch slightly before it enters screen
      threshold: 0.1
    };

    const io = new IntersectionObserver((entries, observer) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          const postNode = entry.target;
          observer.unobserve(postNode);

          if (!processedPosts.has(postNode)) {
            processedPosts.add(postNode);
            curatePost(postNode);
          }
        }
      });
    }, observerOptions);

    // Debounced scan mechanism
    let scanTimeout = null;
    function triggerDebouncedScan() {
      clearTimeout(scanTimeout);
      scanTimeout = setTimeout(() => {
        scanAndRegister(io);
      }, 150);
    }

    const callback = function (mutationsList) {
      let needsScan = false;
      for (const mutation of mutationsList) {
        if (mutation.type === "childList" && mutation.addedNodes.length > 0) {
          needsScan = true;
          break;
        }
        if (mutation.type === "attributes" && ["class", "data-urn", "data-testid"].includes(mutation.attributeName)) {
          needsScan = true;
          break;
        }
      }
      if (needsScan) {
        triggerDebouncedScan();
      }
    };

    const mutationObserver = new MutationObserver(callback);
    mutationObserver.observe(document.documentElement, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ["class", "data-urn", "data-testid"]
    });

    // Initial scan
    scanAndRegister(io);

    // Periodic fallback (lightweight polling)
    setInterval(() => {
      scanAndRegister(io);
    }, 2000);
  }

  // Main curation request routine
  function curatePost(postNode) {
    const authorName = extractAuthorName(postNode);
    const authorUrn = extractAuthorUrn(postNode);
    const postText = extractPostText(postNode);

    safeLog(`[Curate Trigger] Viewport hit: author="${authorName}", textLength=${postText.length}, textSample="${postText.substring(0, 60)}"`);

    // Ignore empty/non-text posts
    if (!postText.trim()) {
      return;
    }

    let finalAuthorUrn = authorUrn;
    if (!finalAuthorUrn) {
      finalAuthorUrn = `/in/unknown-${hashCode(authorName)}`;
    }

    // Since data-urn might be missing, generate a robust fallback URN key
    let postUrn = postNode.getAttribute("data-urn") || `hash:${hashCode(postText.substring(0, 100) + finalAuthorUrn)}`;
    
    fallbackPostMap.set(postUrn, postNode);
    if (fallbackPostMap.size > 150) {
      const oldestKey = fallbackPostMap.keys().next().value;
      fallbackPostMap.delete(oldestKey);
    }

    safeLog(`Viewport entry registered: author="${authorName}", URN="${postUrn}"`);

    // Inline blur feedback while processing
    postNode.style.setProperty("filter", "blur(2px)", "important");
    postNode.style.setProperty("opacity", "0.8", "important");
    postNode.style.setProperty("transition", "filter 0.3s ease, opacity 0.3s ease", "important");

    chrome.runtime.sendMessage({
      action: "curate",
      postData: {
        post_urn: postUrn,
        author_urn: finalAuthorUrn,
        author_name: authorName,
        post_text: postText,
      }
    }, (response) => {
      // Clear visual feedback processing style
      postNode.style.removeProperty("filter");
      postNode.style.removeProperty("opacity");

      if (chrome.runtime.lastError) {
        return;
      }
      if (response && response.success) {
        applyStealthCuration(postNode, response.data, authorName);
      }
    });
  }

  // Applies inline display styles instead of stylesheet classes
  function applyStealthCuration(postNode, curation, authorName) {
    const { action, matched_detector, explanation, post_urn } = curation;

    if (action === "keep") {
      return;
    }

    if (action === "hide" || action === "collapse") {
      const labelMap = {
        ai_slop: "AI Slop Detector",
        fake_expert: "Fake Expert Detector",
        news_aggregator: "News Aggregator Detector",
        sales_pitch: "Sales Pitch Filter",
        humble_brag: "Humble Brag Detector",
        generic_motivation: "Generic Motivation Filter",
        copy_paste_influencer: "Copy-Paste Influencer Detector"
      };

      const detectorName = labelMap[matched_detector] || "Attention Guardian";

      // Shrink card height via inline styles (never display:none to prevent pagination loops)
      postNode.style.setProperty("max-height", "52px", "important");
      postNode.style.setProperty("overflow", "hidden", "important");
      postNode.style.setProperty("position", "relative", "important");
      postNode.style.setProperty("opacity", "0.85", "important");
      postNode.style.setProperty("pointer-events", "none", "important");
      postNode.style.setProperty("border", "1px solid rgba(220, 38, 38, 0.2)", "important");
      postNode.style.setProperty("transition", "max-height 0.3s cubic-bezier(0.16, 1, 0.3, 1), opacity 0.3s ease", "important");

      // Inject absolute overlay, styled entirely inline
      const overlay = document.createElement("div");
      postNode._guardianOverlay = overlay; // store ref in memory (safe isolated world)

      overlay.style.setProperty("position", "absolute", "important");
      overlay.style.setProperty("top", "0", "important");
      overlay.style.setProperty("left", "0", "important");
      overlay.style.setProperty("right", "0", "important");
      overlay.style.setProperty("bottom", "0", "important");
      overlay.style.setProperty("z-index", "100", "important");
      overlay.style.setProperty("background", "rgba(248, 250, 252, 0.98)", "important");
      overlay.style.setProperty("display", "flex", "important");
      overlay.style.setProperty("align-items", "center", "important");
      overlay.style.setProperty("justify-content", "space-between", "important");
      overlay.style.setProperty("padding", "0 16px", "important");
      overlay.style.setProperty("pointer-events", "auto", "important");
      overlay.style.setProperty("font-family", "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif", "important");
      overlay.style.setProperty("border-bottom", "1px solid rgba(0,0,0,0.05)", "important");

      overlay.innerHTML = `
        <div style="display: flex; align-items: center; gap: 8px; font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
          <span style="background: #fee2e2; color: #dc2626; padding: 2px 6px; border-radius: 4px; font-size: 9px; font-weight: 800; text-transform: uppercase;">${detectorName}</span>
          <span style="color: #1e293b; font-weight: 700;">${action === "hide" ? "Hidden" : "Collapsed"} post by <strong>${authorName}</strong></span>
          <span style="color: #64748b; font-size: 11px;">(${explanation || "Low quality"})</span>
        </div>
        <button class="guardian-restore-btn" style="
          background: #ffffff;
          border: 1px solid #cbd5e1;
          border-radius: 6px;
          color: #334155;
          font-size: 11px;
          font-weight: 600;
          padding: 4px 10px;
          cursor: pointer;
          transition: all 0.2s ease;
        ">Restore</button>
      `;

      postNode.appendChild(overlay);

      // Bind restore event
      const restoreBtn = overlay.querySelector(".guardian-restore-btn");
      restoreBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        e.preventDefault();
        
        restorePostStyles(postNode);
        submitCorrection(post_urn, "restore");
      });

      safeLog(`Filtered post by ${authorName} (Reason: ${explanation || matched_detector})`);
    } 
    else if (action === "highlight") {
      // Elegant gold left-border applied inline
      postNode.style.setProperty("border-left", "4px solid #f59e0b", "important");
      postNode.style.setProperty("box-shadow", "0 0 15px rgba(245, 158, 11, 0.15)", "important");
      postNode.style.setProperty("position", "relative", "important");
    }
  }

  function restorePostStyles(postNode) {
    postNode.style.removeProperty("max-height");
    postNode.style.removeProperty("overflow");
    postNode.style.removeProperty("position");
    postNode.style.removeProperty("opacity");
    postNode.style.removeProperty("pointer-events");
    postNode.style.removeProperty("border");
    postNode.style.removeProperty("border-left");
    postNode.style.removeProperty("box-shadow");

    if (postNode._guardianOverlay) {
      postNode._guardianOverlay.remove();
      delete postNode._guardianOverlay;
    }
  }

  // Listens for restore requests dispatched from Popup dashboard
  function setupMessageListener() {
    chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
      if (request.action === "restore_post") {
        const { postUrn } = request;
        
        let postNode = document.querySelector(`div[data-urn="${postUrn}"]`);
        if (!postNode) {
          postNode = fallbackPostMap.get(postUrn);
        }

        if (postNode) {
          restorePostStyles(postNode);
          sendResponse({ success: true });
        } else {
          safeLog(`Element not found in DOM for restore URN: ${postUrn}`);
          sendResponse({ success: false, error: "Post element not found in active feed viewport" });
        }
        return true;
      }
    });
  }

  // Async correction submission
  function submitCorrection(postUrn, action) {
    chrome.runtime.sendMessage({
      action: "correction",
      correctionData: {
        post_urn: postUrn,
        action: action,
      }
    }, (response) => {
      if (chrome.runtime.lastError) {
        safeLog("Correction dispatch error: " + chrome.runtime.lastError.message);
      }
    });
  }

  // Helper to route logs safely to background service worker console
  function safeLog(message, data = "") {
    try {
      chrome.runtime.sendMessage({
        action: "log",
        message: message,
        data: data
      }, () => {
        const err = chrome.runtime.lastError;
      });
    } catch (e) {
      // Fail-silent if context invalidated
    }
  }

  /* --- DOM Extraction Helpers --- */

  function extractAuthorName(postNode) {
    const links = postNode.querySelectorAll('a[href*="/in/"], a[href*="/company/"]');
    for (let i = 0; i < links.length; i++) {
      const text = links[i].innerText.trim().split("\n")[0];
      if (text.length > 0) {
        return text;
      }
    }

    const nameNode = postNode.querySelector(
      '.update-components-actor__title [aria-hidden="true"], ' +
      'span[class*="actor__name"], ' +
      '[class*="actor__title"] span span, ' +
      '.update-components-actor__name'
    );
    if (nameNode) return nameNode.innerText.trim();
    
    return "LinkedIn User";
  }

  function extractAuthorUrn(postNode) {
    const linkNode = postNode.querySelector(
      'a[href*="/in/"], ' +
      'a.update-components-actor__meta-link, ' +
      'a[href*="/company/"], ' +
      'a[href*="/school/"]'
    );
    if (linkNode) {
      const href = linkNode.getAttribute("href");
      try {
        const url = new URL(href, window.location.origin);
        return url.pathname.replace(/\/$/, "");
      } catch {
        return href;
      }
    }
    return "";
  }

  function extractPostText(postNode) {
    const textNode = postNode.querySelector(
      '[data-sdui-anchor-id^="commentary-"], ' +
      '[data-testid="expandable-text-box"], ' +
      '.feed-shared-update-v2__commentary, ' +
      '.update-components-text, ' +
      'span.break-words:not([class*="actor"] *), ' +
      'span[dir="ltr"]:not([class*="actor"] *), ' +
      'span[dir="rtl"]:not([class*="actor"] *), ' +
      '.hasBreakWordsNoHyphen:not([class*="actor"] *)'
    );
    if (textNode) return textNode.innerText.trim();
    return "";
  }

  function hashCode(str) {
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
      hash = str.charCodeAt(i) + ((hash << 5) - hash);
    }
    return Math.abs(hash).toString(16);
  }

  init();
})();
