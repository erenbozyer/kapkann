/**
 * KAPKANN — BİST KAP RAG & Finansal Analiz Web UI Logic
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

  // Application State
  let currentCompany = '';
  let activeSessionId = generateSessionId();
  let chatSessions = loadChatSessions();

  // Initial Setup
  initServerHealthCheck();
  loadCompanies();
  renderHistoryList();
  setupEventListeners();

  /* ──────────────────────────── API & Data ──────────────────────────── */

  async function initServerHealthCheck() {
    try {
      const res = await fetch('/api/health');
      if (res.ok) {
        serverStatus.classList.add('online');
        serverStatus.querySelector('.status-text').textContent = 'KAP Engine Hazır (Online)';
      } else {
        throw new Error();
      }
    } catch (e) {
      serverStatus.classList.remove('online');
      serverStatus.querySelector('.status-text').textContent = 'Sunucu Bağlantı Hatası';
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

  /* ──────────────────────────── Event Listeners ──────────────────────────── */

  function setupEventListeners() {
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

  async function submitQuestion(questionText) {
    if (!questionText) return;

    // Hide Welcome screen
    welcomeContainer.style.display = 'none';

    // Clear input
    chatInput.value = '';
    chatInput.style.height = 'auto';
    sendBtn.disabled = true;

    // 1. Render User Message
    appendUserMessage(questionText);

    // 2. Render Bot Typing Indicator
    const typingElem = appendTypingIndicator();
    scrollToBottom();

    try {
      const payload = {
        question: questionText,
        company: currentCompany || null,
        top_k: 4
      };

      const startTime = performance.now();
      const res = await fetch('/api/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
      const data = await res.json();
      const endTime = performance.now();

      // Remove Typing Indicator
      typingElem.remove();

      // 3. Render Assistant Response
      appendAssistantMessage(data);

      // 4. Save to Session History
      saveMessageToSession(questionText, data);
      renderHistoryList();

    } catch (err) {
      typingElem.remove();
      appendAssistantMessage({
        answer: '⚠️ Bir hata oluştu veya sunucuya erişilemedi. Lütfen `server.py` sunucusunun çalıştığından emin olun.',
        intent: 'HATA',
        sources: [],
        chunks_used: 0,
        query_time_ms: 0
      });
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

  function appendAssistantMessage(data) {
    const wrapper = document.createElement('div');
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
          <span><i class="fa-solid fa-bolt"></i> ${data.query_time_ms || 0}ms</span>
          <span><i class="fa-solid fa-layer-group"></i> ${data.chunks_used || 0} Chunks</span>
        </div>
      </div>
    `;

    messagesList.appendChild(wrapper);
  }

  function appendTypingIndicator() {
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
      appendAssistantMessage(m.responseData);
    });

    renderHistoryList();
    scrollToBottom();
    if (window.innerWidth <= 768) sidebar.classList.remove('active');
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
