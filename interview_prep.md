# LinkedIn Attention Guardian: Interview Prep Sheet

This document explains the architecture of the LinkedIn Attention Guardian, the technical challenges faced, and the solutions implemented.

---

## 1. Project Overview
LinkedIn Attention Guardian is a local Chrome extension that works with a Python (FastAPI) backend to filter low-value posts from a user's LinkedIn feed. 

It uses a hybrid filtering approach to decide whether to block, collapse, or keep a post:
1. **Local SQLite Database**: Checks if a creator has a history of being blocked or whitelisted.
2. **Local Keyword Matching**: Directly blocks obvious posts containing specific words (like "cheat sheet" or "marketing strategy") without using an LLM.
3. **LLM Node (Groq / xAI)**: If local checks are neutral, it uses a LLaMA model to evaluate the post text.

---

## 2. Technical Architecture

### Extension Frontend (JavaScript)
*   **IntersectionObserver (`content.js`)**: Tracks when a post element enters the screen. It only triggers a check for posts the user actually scrolls to, saving API usage.
*   **Visual Feedback**: Temporarily blurs the post while it is being evaluated by the backend.
*   **Request Queue (`background.js`)**: Collects incoming requests and sends them to the backend one-by-one, spaced **2 seconds apart**, to prevent hitting the LLM provider's rate limits.

### Backend Server (FastAPI + LangGraph + SQLite)
1.  **Memory Check**: Checks `curator.db` for the creator's trust score. If the score is very low ($\le$ 0.1) or very high ($\ge$ 0.9), it skips the LLM.
2.  **Keyword Check**: Runs simple text checks for common spam keywords in Python.
3.  **LLM Check**: Sends the text to Groq or xAI for classification if the first two checks are inconclusive.
4.  **Error Handling**: If the LLM call fails (e.g., due to rate limits or network issues), the backend returns `keep` (un-blurring the post) so the user's feed does not freeze.
5.  **Reflection Loop (`reflection.py`)**: If the user clicks "Restore Post" in the popup, it runs an async database task to increase the creator's trust score in SQLite.

---

## 3. Challenges & Solutions

### Challenge 1: Getting clean text from LinkedIn's DOM
*   **Problem**: LinkedIn does not have a single stable feed layout. Homepage feeds and profile activity feeds use different HTML structures. Class names are obfuscated and change frequently.
*   **Solution**: We built a DOM traversal function (`resolvePostCards`) that looks for wrapper elements containing specific attributes (like `data-urn`) and traverses parent nodes to consistently isolate the boundaries of the entire post card.

### Challenge 2: Groq API Rate Limits (429 Errors)
*   **Problem**: Groq's free tier allows a maximum of 30 requests per minute (RPM). Scrolling down a feed quickly triggers this limit, causing API requests to fail.
*   **Solution**: 
    1.  Added a 2-second rate-limiting queue in `background.js` to space out network requests.
    2.  Added direct local keyword heuristics in Python to block obvious spam immediately, bypassing the LLM.

### Challenge 3: Windows Localhost Network Conflicts
*   **Problem**: The extension failed to communicate with the FastAPI backend, logging `Failed to fetch`. Chrome resolved the text string `localhost` to the IPv6 address `[::1]`, while uvicorn was listening only on IPv4 `127.0.0.1`.
*   **Solution**: Changed all occurrences of `localhost` in the extension scripts to the direct IPv4 loopback IP `127.0.0.1`.

---

## 4. Key Engineering Decisions to Mention

*   **Paced Requests**: Spacing client requests sequentially to remain compliant with third-party API limits.
*   **Fail-Open Safety**: Ensuring that external API failures do not break the core user interface by defaulting to showing the post.
*   **Caching & Rules First**: Using local database scores and simple keyword lookups to minimize expensive LLM calls.
