/**
 * KAPKANN — BİST KAP RAG & Finansal Analiz Web UI Logic
 * Dynamic DB Stats & Fact-Engine RAG Pipeline (ONLINE Groq / LOCAL Foundry Toggle)
 */

document.addEventListener('DOMContentLoaded', () => {
  // DOM Elements
  const sidebar = document.getElementById('sidebar');
  const openSidebarBtn = document.getElementById('openSidebarBtn');
  const closeSidebarBtn = document.getElementById('closeSidebarBtn');
  const companySelect = document.getElementById('companySelect');
  const activeCompanyBadge = document.getElementById('activeCompanyBadge');
  const inputActiveTag = document.getElementById('inputActiveTag');
  const inputTagText = document.getElementById('inputTagText');
  const removeInputTag = document.getElementById('removeInputTag');
  const newChatBtn = document.getElementById('newChatBtn');
  const clearChatBtn = document.getElementById('clearChatBtn');
  const historyList = document.getElementById('historyList');
  const welcomeContainer = document.getElementById('welcomeContainer');
  const messagesList = document.getElementById('messagesList');
  const chatInput = document.getElementById('chatInput');
  const sendBtn = document.getElementById('sendBtn');
  const serverStatus = document.getElementById('serverStatus');
  const chunkCountText = document.getElementById('chunkCountText');
  const companyCountText = document.getElementById('companyCountText');

  const btnOnline = document.getElementById('btnOnline');
  const btnLocal = document.getElementById('btnLocal');

  // Application State
  let currentCompany = '';
  let currentProvider = 'groq'; // Default to Groq ONLINE
  let activeSessionId = generateSessionId();
  let chatSessions = loadChatSessions();

  // Initial Setup
  initServerHealthCheck();
  loadStats();
  loadCompanies();
  renderHistoryList();
  setupEventListeners();

  /* ──────────────────────────── API & Data ──────────────────────────── */

  async function initServerHealthCheck() {
    try {
      const res = await fetch('/api/health');
      if (res.ok) {
        const h = await res.json();
        serverStatus.classList.add('online');
        serverStatus.querySelector('.status-text').textContent = `KAP Engine Hazır (${h.provider || 'Online'})`;
      } else {
        throw new Error();
      }
    } catch (e) {
      serverStatus.classList.remove('online');
      serverStatus.querySelector('.status-text').textContent = 'Sunucu Bağlantı Hatası';
    }
  }

  async function loadStats() {
    try {
      const res = await fetch('/api/stats');
      if (!res.ok) return;
      const stats = await res.json();
      
      if (chunkCountText) chunkCountText.textContent = stats.total_chunks ? stats.total_chunks.toLocaleString('tr-TR') : '12.450';
      if (companyCountText) companyCountText.textContent = stats.total_companies || '10';
    } catch (err) {
      if (chunkCountText) chunkCountText.textContent = '12.450';
      if (companyCountText) companyCountText.textContent = '10';
    }
  }

  async function loadCompanies() {
    try {
      const res = await fetch('/api/companies');
      if (!res.ok) return;
      const companies = await res.json();
      
      companySelect.innerHTML = '<option value="">Tüm Şirketler (Genel Arama)</option>';
      companies.forEach(c => {
        const opt = document.createElement('option');
        opt.value = c.code;
        opt.textContent = `${c.code} — ${c.name || ''}`;
        companySelect.appendChild(opt);
      });
    } catch (err) {
      console.warn('Şirketler listesi yüklenemedi:', err);
    }
  }

  function setProvider(prov) {
    currentProvider = prov;
    document.querySelectorAll('.provider-switch-btn').forEach(btn => {
      const btnProv = btn.dataset.provider || (btn.classList.contains('online') ? 'groq' : 'local');
      if (btnProv === prov) {
        btn.classList.add('active');
      } else {
        btn.classList.remove('active');
      }
    });
  }

  /* ──────────────────────────── Event Listeners ──────────────────────────── */

  function setupEventListeners() {
    // View Navigation Buttons (Header & Sidebar Tabs)
    document.querySelectorAll('[data-view]').forEach(btn => {
      btn.addEventListener('click', () => {
        const viewName = btn.getAttribute('data-view');
        setActiveView(viewName);
        if (window.innerWidth <= 768) sidebar.classList.remove('active');
      });
    });

    // BİST 100 Search & Filter Listeners
    const bistSearchInput = document.getElementById('bistSearchInput');
    const btnRefreshBist100 = document.getElementById('btnRefreshBist100');

    bistSearchInput?.addEventListener('input', renderBist100Table);

    document.querySelectorAll('.bist-filter-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.bist-filter-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        currentBistFilter = btn.getAttribute('data-filter') || 'all';
        renderBist100Table();
      });
    });

    btnRefreshBist100?.addEventListener('click', () => {
      fetchBist100Data();
    });

    // Provider Toggle Switch (ONLINE / LOCAL) - Header & Sidebar Sync
    document.querySelectorAll('.provider-switch-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const prov = btn.dataset.provider || (btn.classList.contains('online') ? 'groq' : 'local');
        setProvider(prov);
      });
    });

    // Mobile Sidebar Toggle
    openSidebarBtn?.addEventListener('click', () => sidebar.classList.add('active'));
    closeSidebarBtn?.addEventListener('click', () => sidebar.classList.remove('active'));

    // Company Select Change
    companySelect?.addEventListener('change', (e) => {
      setCompany(e.target.value);
    });

    removeInputTag?.addEventListener('click', () => {
      setCompany('');
      companySelect.value = '';
    });

    // New Chat Button
    newChatBtn?.addEventListener('click', startNewChat);

    // Clear Chat Button
    clearChatBtn?.addEventListener('click', () => {
      messagesList.innerHTML = '';
      welcomeContainer.style.display = 'flex';
      deleteCurrentSession();
    });

    // Quick Cards Click
    document.querySelectorAll('.quick-card').forEach(card => {
      card.addEventListener('click', () => {
        const prompt = card.getAttribute('data-prompt');
        let fullQuestion = prompt;
        if (currentCompany) {
          fullQuestion = `${currentCompany} ${prompt}`;
        } else {
          fullQuestion = `THYAO ${prompt}`;
          setCompany('THYAO');
          companySelect.value = 'THYAO';
        }
        submitQuestion(fullQuestion);
      });
    });

    // Demo Sample Question Cards Click
    document.querySelectorAll('.demo-question-card').forEach(card => {
      card.addEventListener('click', () => {
        const comp = card.getAttribute('data-company');
        const q = card.getAttribute('data-q');
        if (comp) {
          setCompany(comp);
          companySelect.value = comp;
        }
        submitQuestion(q);
      });
    });

    // Template Chips Click
    document.querySelectorAll('.template-chip').forEach(chip => {
      chip.addEventListener('click', () => {
        const type = chip.getAttribute('data-template');
        const comp = currentCompany || 'THYAO';
        if (!currentCompany) {
          setCompany('THYAO');
          companySelect.value = 'THYAO';
        }

        const templates = {
          bilanco: `${comp} bilanço karnesi ve borçluluk durumu nasıl?`,
          gelir: `${comp} ciro ve net dönem karı ne kadar?`,
          temettu: `${comp} temettü dağıtacak mı, kar payı kararı var mı?`,
          yatirim: `${comp} yeni iş ilişkisi veya yatırım duyurdu mu?`,
          genel: `${comp} son KAP bildirimlerinde öne çıkanlar nelerdir?`
        };

        submitQuestion(templates[type] || `${comp} analiz`);
      });
    });

    // Textarea Auto Resize & Input State
    chatInput?.addEventListener('input', () => {
      chatInput.style.height = 'auto';
      chatInput.style.height = `${Math.min(chatInput.scrollHeight, 150)}px`;
      sendBtn.disabled = !chatInput.value.trim();
    });

    chatInput?.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        const text = chatInput.value.trim();
        if (text) {
          submitQuestion(text);
        }
      }
    });

    sendBtn?.addEventListener('click', () => {
      const text = chatInput.value.trim();
      if (text) {
        submitQuestion(text);
      }
    });
  }

  /* ──────────────────────────── State Management ──────────────────────────── */

  function setCompany(code) {
    currentCompany = code ? code.toUpperCase() : '';
    const nameSpan = activeCompanyBadge.querySelector('.company-badge-name');
    
    if (currentCompany) {
      nameSpan.textContent = currentCompany;
      inputTagText.textContent = currentCompany;
      inputActiveTag.style.display = 'inline-flex';
    } else {
      nameSpan.textContent = 'Tüm Şirketler';
      inputActiveTag.style.display = 'none';
    }
  }

  function startNewChat() {
    activeSessionId = generateSessionId();
    messagesList.innerHTML = '';
    welcomeContainer.style.display = 'flex';
    renderHistoryList();
    if (window.innerWidth <= 768) sidebar.classList.remove('active');
  }

  /* ──────────────────────────── Chat Messaging ──────────────────────────── */

  async function submitQuestion(questionText, forceRefresh = false, targetWrapper = null) {
    if (!questionText) return;

    welcomeContainer.style.display = 'none';

    if (!targetWrapper) {
      chatInput.value = '';
      chatInput.style.height = 'auto';
      sendBtn.disabled = true;

      // 1. Render User Message
      appendUserMessage(questionText);
    }

    // 2. Render or reuse Assistant Message element
    let wrapper = targetWrapper;
    let typingElem = null;

    const providerText = currentProvider === 'groq' ? 'Groq Llama-3.3 / Qwen-27B (Online)' : 'Local Foundry Phi-4 (Offline)';

    if (!wrapper) {
      typingElem = appendTypingIndicator(providerText);
    } else {
      wrapper.querySelector('.message-bubble').innerHTML = `
        <div class="typing-indicator">
          <div class="typing-dot"></div>
          <div class="typing-dot"></div>
          <div class="typing-dot"></div>
          <span style="font-size:0.8rem; color:var(--text-muted); margin-left:0.5rem;">${providerText} yanıt üretiyor...</span>
        </div>
      `;
    }
    scrollToBottom();

    try {
      const payload = {
        question: questionText,
        company: currentCompany || null,
        top_k: 12,
        force_refresh: forceRefresh,
        provider: currentProvider
      };

      const res = await fetch('/api/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
      const data = await res.json();

      if (typingElem) typingElem.remove();

      // 3. Render Assistant Response
      const newWrapper = renderAssistantMessage(data, questionText, wrapper);
      if (!wrapper) messagesList.appendChild(newWrapper);

      // 4. Save to Session History
      saveMessageToSession(questionText, data);
      renderHistoryList();

    } catch (err) {
      if (typingElem) typingElem.remove();
      const errWrapper = renderAssistantMessage({
        answer: '⚠️ Bir hata oluştu veya sunucuya erişilemedi. Lütfen `server.py` sunucusunun çalıştığından emin olun.',
        intent: 'HATA',
        sources: [],
        chunks_used: 0,
        query_time_ms: 0,
        cached: false
      }, questionText, wrapper);
      if (!wrapper) messagesList.appendChild(errWrapper);
    } finally {
      scrollToBottom();
    }
  }

  function appendUserMessage(text) {
    const wrapper = document.createElement('div');
    wrapper.className = 'message-wrapper user';
    wrapper.innerHTML = `
      <div class="message-avatar">
        <i class="fa-solid fa-user"></i>
      </div>
      <div class="message-content">
        <div class="message-bubble">${escapeHtml(text)}</div>
      </div>
    `;
    messagesList.appendChild(wrapper);
  }

  function renderAssistantMessage(data, questionText, existingWrapper = null) {
    const wrapper = existingWrapper || document.createElement('div');
    wrapper.className = 'message-wrapper assistant';

    const intentBadges = {
      BILANCO: '📊 Mod: Bilanço & Likidite Karnesi',
      GELIR: '📈 Mod: Gelir & Karlılık Analizi',
      TEMETTU: '💰 Mod: Temettü & Sermaye Artırımı',
      YATIRIM: '🤝 Mod: Yeni İş & Yatırım Raporu',
      GENEL: '📰 Mod: Genel KAP Analizi'
    };

    const intentText = intentBadges[data.intent] || `🎯 Mod: ${data.intent || 'GENEL'}`;
    const parsedHtml = marked.parse(data.answer || '');

    // Cache Tag
    const cacheTagHtml = data.cached
      ? `<div class="cache-badge-tag"><i class="fa-solid fa-bolt"></i> Önbellekten Getirildi (${(data.query_time_ms / 1000).toFixed(2)}s)</div>`
      : `<div class="cache-badge-tag" style="background:rgba(99,102,241,0.15); color:var(--primary); border-color:var(--primary-glow);"><i class="fa-solid fa-robot"></i> Canlı AI Yanıtı (${currentProvider.toUpperCase()})</div>`;

    // Sources List
    let sourcesHtml = '';
    if (data.sources && data.sources.length > 0) {
      const items = data.sources.map((src, i) => `
        <div class="source-item">
          <span class="source-title">
            ${i+1}. [${src.date || ''}] ${src.company || ''} (${src.type || 'KAP'}) — ${escapeHtml(src.title || '')}
          </span>
          <a href="${src.url || '#'}" target="_blank" rel="noopener" class="source-link">
            KAP <i class="fa-solid fa-arrow-up-right-from-square"></i>
          </a>
        </div>
      `).join('');

      sourcesHtml = `
        <div class="sources-card">
          <div class="sources-header">
            <i class="fa-solid fa-paperclip"></i> Kullanılan KAP Kaynakları (${data.sources.length}):
          </div>
          <div class="sources-list">${items}</div>
        </div>
      `;
    }

    wrapper.innerHTML = `
      <div class="message-avatar">
        <i class="fa-solid fa-robot"></i>
      </div>
      <div class="message-content">
        <div class="message-header-tag">${intentText}</div>
        <div class="message-bubble">${parsedHtml}</div>
        ${sourcesHtml}
        <div class="message-meta">
          <span><i class="fa-solid fa-clock"></i> ${data.query_time_ms || 0}ms</span>
          <span><i class="fa-solid fa-layer-group"></i> ${data.chunks_used || 0} Chunks</span>
        </div>
        
        <!-- Feedback & Cache Footer -->
        <div class="feedback-container">
          ${cacheTagHtml}
          <div class="feedback-question">
            <span>Bu cevaptan memnun musunuz?</span>
            <button class="btn-feedback btn-yes" title="Evet, memnunum">
              <i class="fa-solid fa-thumbs-up"></i> Evet
            </button>
            <button class="btn-feedback btn-no" title="Hayır, AI ile Yeniden Üret">
              <i class="fa-solid fa-rotate"></i> Yeniden Üret
            </button>
          </div>
          <div class="feedback-thanks" style="display:none;">
            <i class="fa-solid fa-heart"></i> Geri bildiriminiz için teşekkürler!
          </div>
        </div>
      </div>
    `;

    // Event Listeners for Feedback Buttons
    const btnYes = wrapper.querySelector('.btn-yes');
    const btnNo = wrapper.querySelector('.btn-no');
    const feedbackQuestion = wrapper.querySelector('.feedback-question');
    const feedbackThanks = wrapper.querySelector('.feedback-thanks');

    btnYes?.addEventListener('click', () => {
      feedbackQuestion.style.display = 'none';
      feedbackThanks.style.display = 'flex';
    });

    btnNo?.addEventListener('click', () => {
      submitQuestion(questionText, true, wrapper);
    });

    return wrapper;
  }

  function appendTypingIndicator(providerText = '') {
    const wrapper = document.createElement('div');
    wrapper.className = 'message-wrapper assistant';
    wrapper.innerHTML = `
      <div class="message-avatar">
        <i class="fa-solid fa-robot"></i>
      </div>
      <div class="message-content">
        <div class="message-bubble">
          <div class="typing-indicator">
            <div class="typing-dot"></div>
            <div class="typing-dot"></div>
            <div class="typing-dot"></div>
            <span style="font-size:0.8rem; color:var(--text-muted); margin-left:0.5rem;">${providerText} analiz yapıyor...</span>
          </div>
        </div>
      </div>
    `;
    messagesList.appendChild(wrapper);
    return wrapper;
  }

  /* ──────────────────────────── LocalStorage History ──────────────────────────── */

  function loadChatSessions() {
    try {
      return JSON.parse(localStorage.getItem('kapkann_sessions')) || {};
    } catch {
      return {};
    }
  }

  function saveMessageToSession(question, responseData) {
    if (!chatSessions[activeSessionId]) {
      chatSessions[activeSessionId] = {
        id: activeSessionId,
        title: question.length > 30 ? question.substring(0, 30) + '...' : question,
        company: currentCompany,
        timestamp: Date.now(),
        messages: []
      };
    }

    chatSessions[activeSessionId].messages.push({
      question,
      responseData
    });

    localStorage.setItem('kapkann_sessions', JSON.stringify(chatSessions));
  }

  function deleteCurrentSession() {
    delete chatSessions[activeSessionId];
    localStorage.setItem('kapkann_sessions', JSON.stringify(chatSessions));
    startNewChat();
  }

  function renderHistoryList() {
    if (!historyList) return;
    historyList.innerHTML = '';

    const sessions = Object.values(chatSessions).sort((a, b) => b.timestamp - a.timestamp);

    if (sessions.length === 0) {
      historyList.innerHTML = '<div style="font-size:0.75rem; color:var(--text-dark); text-align:center; padding:1rem;">Henüz geçmiş sohbet yok.</div>';
      return;
    }

    sessions.forEach(sess => {
      const item = document.createElement('div');
      item.className = `history-item ${sess.id === activeSessionId ? 'active' : ''}`;
      
      const icon = sess.company ? `🏢 ${sess.company}` : '💬';
      item.innerHTML = `
        <span>${icon} ${escapeHtml(sess.title)}</span>
        <i class="fa-solid fa-trash-can btn-del-hist"></i>
      `;

      item.querySelector('span').addEventListener('click', () => restoreSession(sess.id));
      item.querySelector('.btn-del-hist').addEventListener('click', (e) => {
        e.stopPropagation();
        delete chatSessions[sess.id];
        localStorage.setItem('kapkann_sessions', JSON.stringify(chatSessions));
        if (sess.id === activeSessionId) startNewChat();
        else renderHistoryList();
      });

      historyList.appendChild(item);
    });
  }

  function restoreSession(sessionId) {
    const sess = chatSessions[sessionId];
    if (!sess) return;

    activeSessionId = sessionId;
    currentCompany = sess.company || '';
    if (companySelect) companySelect.value = currentCompany;
    setCompany(currentCompany);

    welcomeContainer.style.display = 'none';
    messagesList.innerHTML = '';

    sess.messages.forEach(m => {
      appendUserMessage(m.question);
      const w = renderAssistantMessage(m.responseData, m.question);
      messagesList.appendChild(w);
    });

    renderHistoryList();
    scrollToBottom();
    if (window.innerWidth <= 768) sidebar.classList.remove('active');
  }

  /* ──────────────────────────── BİST 100 Canlı Borsa Logic ──────────────────────────── */

  let bist100Data = [];
  let currentBistFilter = 'all'; // 'all', 'up', 'down'
  let bistAutoRefreshTimer = null;

  function setActiveView(viewName) {
    const viewChat = document.getElementById('viewChat');
    const viewBist100 = document.getElementById('viewBist100');
    const headerMainTitle = document.getElementById('headerMainTitle');

    document.querySelectorAll('[data-view]').forEach(btn => {
      if (btn.getAttribute('data-view') === viewName) {
        btn.classList.add('active');
      } else {
        btn.classList.remove('active');
      }
    });

    if (viewName === 'bist100') {
      if (viewChat) viewChat.style.display = 'none';
      if (viewBist100) viewBist100.style.display = 'flex';
      if (headerMainTitle) headerMainTitle.textContent = 'BİST 100 Canlı Borsa';
      fetchBist100Data();
      startBistAutoRefresh();
    } else {
      if (viewBist100) viewBist100.style.display = 'none';
      if (viewChat) viewChat.style.display = 'flex';
      if (headerMainTitle) headerMainTitle.textContent = 'KAP Finansal RAG Asistanı';
      stopBistAutoRefresh();
    }
  }

  async function fetchBist100Data() {
    const tableBody = document.getElementById('bist100TableBody');
    const btnRefresh = document.getElementById('btnRefreshBist100');

    if (btnRefresh) {
      const icon = btnRefresh.querySelector('i');
      if (icon) icon.classList.add('fa-spin');
    }

    try {
      const res = await fetch('/api/bist100');
      if (!res.ok) throw new Error('BİST 100 verisi çekilemedi');
      const data = await res.json();

      bist100Data = data.items || [];
      renderBist100Stats(data.stats, data.updated_at);
      renderBist100Table();
    } catch (err) {
      if (tableBody && bist100Data.length === 0) {
        tableBody.innerHTML = `<tr><td colspan="10" style="text-align:center; padding:2rem; color:var(--accent-rose);">⚠️ BİST 100 verisi alınamadı. Lütfen sunucu bağlantısını kontrol edin.</td></tr>`;
      }
    } finally {
      if (btnRefresh) {
        const icon = btnRefresh.querySelector('i');
        if (icon) icon.classList.remove('fa-spin');
      }
    }
  }

  function renderBist100Stats(stats = {}, updatedAt = '') {
    const totalElem = document.getElementById('bistTotalCount');
    const upElem = document.getElementById('bistUpCount');
    const downElem = document.getElementById('bistDownCount');
    const neutralElem = document.getElementById('bistNeutralCount');
    const updatedElem = document.getElementById('bistUpdatedAt');

    if (totalElem) totalElem.textContent = stats.total || bist100Data.length || '100';
    if (upElem) upElem.textContent = stats.up || '0';
    if (downElem) downElem.textContent = stats.down || '0';
    if (neutralElem) neutralElem.textContent = stats.neutral || '0';
    if (updatedElem) updatedElem.textContent = updatedAt || new Date().toLocaleTimeString('tr-TR');
  }

  function renderBist100Table() {
    const tableBody = document.getElementById('bist100TableBody');
    const searchInput = document.getElementById('bistSearchInput');
    if (!tableBody) return;

    const searchTerm = searchInput ? searchInput.value.trim().toUpperCase() : '';

    const filtered = bist100Data.filter(item => {
      // Filter by direction
      if (currentBistFilter === 'up' && item.direction !== 'up') return false;
      if (currentBistFilter === 'down' && item.direction !== 'down') return false;

      // Filter by search term
      if (searchTerm && !item.code.includes(searchTerm)) return false;

      return true;
    });

    if (filtered.length === 0) {
      tableBody.innerHTML = `<tr><td colspan="10" style="text-align:center; padding:2rem; color:var(--text-muted);">Aramanıza uygun hisse bulunamadı.</td></tr>`;
      return;
    }

    tableBody.innerHTML = filtered.map(item => {
      const isUp = item.direction === 'up';
      const isDown = item.direction === 'down';
      const badgeClass = isUp ? 'up' : (isDown ? 'down' : 'neutral');
      const icon = isUp ? '<i class="fa-solid fa-caret-up"></i>' : (isDown ? '<i class="fa-solid fa-caret-down"></i>' : '');

      return `
        <tr>
          <td><span class="bist-code-badge">${item.code}</span></td>
          <td><strong>${item.last_price} TL</strong></td>
          <td><span class="pct-badge ${badgeClass}">${icon} ${item.change_pct}</span></td>
          <td style="color:var(--text-muted);">${item.bid}</td>
          <td style="color:var(--text-muted);">${item.ask}</td>
          <td style="font-size:0.8rem; color:var(--accent-rose);">${item.low}</td>
          <td style="font-size:0.8rem; color:var(--accent-emerald);">${item.high}</td>
          <td style="font-size:0.8rem; color:var(--text-muted);">${item.aof}</td>
          <td style="font-size:0.8rem; color:var(--text-main);">${item.volume_tl} TL</td>
          <td style="text-align:center;">
            <button class="btn-ai-analyze" data-code="${item.code}">
              <i class="fa-solid fa-robot"></i> AI Analiz
            </button>
          </td>
        </tr>
      `;
    }).join('');

    // Bind AI Analyze buttons
    tableBody.querySelectorAll('.btn-ai-analyze').forEach(btn => {
      btn.addEventListener('click', () => {
        const code = btn.getAttribute('data-code');
        if (code) {
          setCompany(code);
          if (companySelect) companySelect.value = code;
          setActiveView('chat');
          submitQuestion(`${code} bilanço karnesi ve borçluluk durumu nasıl?`);
        }
      });
    });
  }

  function startBistAutoRefresh() {
    stopBistAutoRefresh();
    bistAutoRefreshTimer = setInterval(() => {
      fetchBist100Data();
    }, 60000); // 1 minute auto-refresh
  }

  function stopBistAutoRefresh() {
    if (bistAutoRefreshTimer) {
      clearInterval(bistAutoRefreshTimer);
      bistAutoRefreshTimer = null;
    }
  }

  /* ──────────────────────────── Utilities ──────────────────────────── */

  function generateSessionId() {
    return 'sess_' + Date.now() + '_' + Math.random().toString(36).substr(2, 6);
  }

  function scrollToBottom() {
    const chatBody = document.getElementById('chatBody');
    if (chatBody) {
      chatBody.scrollTop = chatBody.scrollHeight;
    }
  }

  function escapeHtml(str) {
    return str.replace(/[&<>"']/g, function(m) {
      return {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#039;'
      }[m];
    });
  }
});
