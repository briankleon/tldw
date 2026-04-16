// ── STATE ─────────────────────────────────────────────────────────────
let currentData = null;
let chatHistory = [];
let ragReady = false;
let goDeeperPolling = null;

const LEVEL_COLORS = [
  '#d4410a', '#e8650d', '#f0920a', '#3a7fd4', '#1a5fb4',
  '#7a3aad', '#0a9460', '#8a6a10', '#6a3a0a'
];


// ── INIT ──────────────────────────────────────────────────────────────
document.getElementById('urlInput').addEventListener('keydown', e => {
  if (e.key === 'Enter') handleSubmit();
});

document.addEventListener('DOMContentLoaded', () => {
  const chatInput = document.getElementById('chatInput');
  if (chatInput) {
    chatInput.addEventListener('keydown', e => {
      if (e.key === 'Enter') sendChatMessage();
    });
  }
});

function tryExample(url) {
  document.getElementById('urlInput').value = url;
  handleSubmit();
}

function goHome() {
  show('landing');
  document.getElementById('urlInput').value = '';
  currentData = null;
  chatHistory = [];
  ragReady = false;
  if (goDeeperPolling) {
    clearInterval(goDeeperPolling);
    goDeeperPolling = null;
  }
  // Reset Go Deeper to hidden state for next video
  const section = document.getElementById('goDeeperSection');
  if (section) section.style.display = 'none';
  const content = document.getElementById('goDeeperContent');
  if (content) content.innerHTML = '';
}

function show(id) {
  ['landing', 'loading', 'result'].forEach(v => {
    document.getElementById(v).classList.toggle('hidden', v !== id);
  });
}

// ── LEFT PANEL SIZING ─────────────────────────────────────────────────
// Explicitly sets result-left height so left-scroll-area + chat section
// always fit exactly in the viewport — no reliance on flex-chain assumptions.
function sizeLeftPanel() {
  const header = document.querySelector('.result-header');
  const left   = document.querySelector('.result-left');
  if (!header || !left) return;
  left.style.height = (window.innerHeight - header.offsetHeight) + 'px';
}

window.addEventListener('resize', () => {
  if (!document.getElementById('result').classList.contains('hidden')) {
    sizeLeftPanel();
  }
});

// ── SUBMIT ────────────────────────────────────────────────────────────
async function handleSubmit() {
  const url = document.getElementById('urlInput').value.trim();
  if (!url) {
    document.getElementById('urlInput').focus();
    return;
  }

  show('loading');
  animateLoading();

  try {
    const res = await fetch('/api/summarise', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url })
    });

    const data = await res.json();

    if (!res.ok) {
      throw new Error(data.detail || 'Something went wrong');
    }

    currentData = data;
    renderResult(data);
  } catch (err) {
    show('landing');
    showError(err.message);
  }
}

// ── LOADING ANIMATION ─────────────────────────────────────────────────
function animateLoading() {
  const bar = document.getElementById('loadingBar');
  const steps = [
    { id: 'ls1', delay: 0, progress: 30 },
    { id: 'ls2', delay: 1200, progress: 65 },
    { id: 'ls3', delay: 2400, progress: 88 },
  ];

  // Reset
  document.querySelectorAll('.ls').forEach(el => {
    el.classList.remove('done');
    el.classList.add('dim');
  });
  document.getElementById('ls1').classList.remove('dim');
  bar.style.width = '0%';

  steps.forEach(({ id, delay, progress }) => {
    setTimeout(() => {
      const el = document.getElementById(id);
      if (el) {
        el.classList.remove('dim');
        bar.style.width = progress + '%';
        // Mark previous as done
        if (id === 'ls2') document.getElementById('ls1').classList.add('done');
        if (id === 'ls3') document.getElementById('ls2').classList.add('done');
      }
    }, delay);
  });
}

// ── RENDER RESULT ─────────────────────────────────────────────────────
function renderResult(data) {
  // Finish loading bar
  document.getElementById('loadingBar').style.width = '100%';

  setTimeout(() => {
    show('result');
    sizeLeftPanel(); // pin left panel to exact viewport height before rendering content

    // Thumbnail
    const videoId = data.video_id;
    document.getElementById('videoThumb').src = `https://img.youtube.com/vi/${videoId}/mqdefault.jpg`;
    document.getElementById('videoLink').href = `https://www.youtube.com/watch?v=${videoId}`;

    // Header badge
    const typeLabels = {
      hierarchy: '▲ Hierarchy',
      timeline: '→ Timeline',
      graph: '◉ Concept Graph',
      comparison: '⊞ Comparison',
      stat_cards: '⊡ Stat Cards'
    };
    document.getElementById('vtBadge').textContent = typeLabels[data.visual_type] || data.visual_type;

    // TLDR
    document.getElementById('videoTitle').textContent = data.video_title || '';
    document.getElementById('tldrText').textContent = data.tldr || '';
    document.getElementById('visualReason').textContent = '↳ ' + (data.visual_reason || '');

    // Visual
    const container = document.getElementById('visualContainer');
    container.innerHTML = '';
    renderVisual(data.visual_type, data.content, container);

    // Initialize chat
    initChat();

    // Initialize Go Deeper
    initGoDeeper(data.video_id);
  }, 300);
}

// ── GO DEEPER ─────────────────────────────────────────────────────────
function initGoDeeper(videoId) {
  const section = document.getElementById('goDeeperSection');
  const content = document.getElementById('goDeeperContent');

  // Start hidden — only reveal once we know results are coming
  section.style.display = 'none';
  content.innerHTML = '';

  if (goDeeperPolling) clearInterval(goDeeperPolling);
  pollGoDeeper(videoId);
  goDeeperPolling = setInterval(() => pollGoDeeper(videoId), 3000);
}

async function pollGoDeeper(videoId) {
  try {
    const res = await fetch(`/api/go-deeper/${videoId}`);
    const data = await res.json();
    const section = document.getElementById('goDeeperSection');
    const content = document.getElementById('goDeeperContent');

    if (data.status === 'processing') {
      // Task is running — reveal section with skeletons
      section.style.display = '';
      if (!content.querySelector('.skeleton') && !content.querySelector('.resource-card')) {
        content.innerHTML = `
          <div class="resource-card skeleton"></div>
          <div class="resource-card skeleton"></div>
          <div class="resource-card skeleton"></div>
        `;
      }

    } else if (data.status === 'completed') {
      if (goDeeperPolling) { clearInterval(goDeeperPolling); goDeeperPolling = null; }

      if (data.resources && data.resources.length > 0) {
        section.style.display = '';  // reveal
        renderGoDeeper(data.resources);
      }
      // If no resources → section stays hidden, nothing shown (Tavily not configured)

    } else if (data.status === 'error') {
      if (goDeeperPolling) { clearInterval(goDeeperPolling); goDeeperPolling = null; }
      // Stay hidden — error is silent, core flow unaffected
    }
    // 'not_started' → keep hidden, keep polling

  } catch (err) {
    console.error('Go Deeper polling error:', err);
  }
}

function renderGoDeeper(resources) {
  const content = document.getElementById('goDeeperContent');
  content.innerHTML = '';

  resources.forEach((resource, i) => {
    const card = document.createElement('div');
    card.className = 'resource-card';
    card.style.animationDelay = `${i * 0.08}s`;

    const typeBadge = document.createElement('div');
    typeBadge.className = `resource-type resource-type-${resource.type || 'article'}`;
    typeBadge.textContent = resource.type || 'article';

    const title = document.createElement('div');
    title.className = 'resource-title';
    title.textContent = resource.title || 'Resource';

    const source = document.createElement('div');
    source.className = 'resource-source';
    source.textContent = resource.source || 'Unknown';

    const reason = document.createElement('div');
    reason.className = 'resource-reason';
    reason.textContent = resource.reason || 'Related to video content';

    const link = document.createElement('a');
    link.className = 'resource-link';
    link.href = resource.url || '#';
    link.target = '_blank';
    link.rel = 'noopener';
    link.textContent = 'Read →';

    card.appendChild(typeBadge);
    card.appendChild(title);
    card.appendChild(source);
    card.appendChild(reason);
    card.appendChild(link);

    content.appendChild(card);
  });
}

// ── CHAT ──────────────────────────────────────────────────────────────
function initChat() {
  chatHistory = [];
  ragReady = false;

  // Reset chat UI
  const messages = document.getElementById('chatMessages');
  const status = document.getElementById('chatStatus');

  messages.innerHTML = `
    <div class="chat-welcome">
      <span class="chat-welcome-icon">💬</span>
      <p>Ask anything about this video — I've read the full transcript.</p>
    </div>
  `;
  document.getElementById('chatInput').value = '';

  // Reset status badge classes
  status.className = 'chat-status preparing';
  status.textContent = 'Preparing Q&A...';

  // After 2s the RAG index built in background is ready
  setTimeout(() => {
    ragReady = true;
    status.className = 'chat-status ready';
    status.textContent = 'Ready';
  }, 2500);
}

async function sendChatMessage() {
  const input = document.getElementById('chatInput');
  const sendBtn = document.getElementById('chatSendBtn');
  const question = input.value.trim();

  if (!question) return;
  if (!currentData || !currentData.video_id) {
    showError('No video loaded');
    return;
  }

  // Clear welcome message on first real message
  const messages = document.getElementById('chatMessages');
  const welcome = messages.querySelector('.chat-welcome');
  if (welcome) welcome.remove();

  // Clear input, disable button
  input.value = '';
  sendBtn.disabled = true;

  // Add user message to UI
  addChatBubble('user', question);

  // Show typing indicator
  const typingId = addChatBubble('assistant', '...');

  try {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        video_id: currentData.video_id,
        question: question,
        chat_history: chatHistory
      })
    });

    const data = await res.json();

    if (!res.ok) {
      throw new Error(data.detail || 'Something went wrong');
    }

    // Remove typing indicator
    document.getElementById(typingId).remove();

    // Add AI response
    addChatBubble('assistant', data.answer);

    // Update chat history
    chatHistory.push({ role: 'user', content: question });
    chatHistory.push({ role: 'assistant', content: data.answer });

  } catch (err) {
    document.getElementById(typingId).remove();
    addChatBubble('assistant', 'Sorry, I encountered an error. Please try again.');
    showError(err.message);
  } finally {
    sendBtn.disabled = false;
    input.focus();
  }
}

function addChatBubble(role, text) {
  const container = document.getElementById('chatMessages');
  const bubble = document.createElement('div');
  const bubbleId = `bubble-${Date.now()}-${Math.random()}`;
  bubble.id = bubbleId;
  bubble.className = `chat-bubble chat-bubble-${role}`;
  bubble.textContent = text;
  container.appendChild(bubble);

  // Scroll to bottom
  container.scrollTop = container.scrollHeight;

  return bubbleId;
}

// ── ERROR ─────────────────────────────────────────────────────────────
function showError(msg) {
  const toast = document.getElementById('errorToast');
  document.getElementById('errorMsg').textContent = msg;
  toast.classList.remove('hidden');
  setTimeout(() => toast.classList.add('hidden'), 6000);
}

function dismissError() {
  document.getElementById('errorToast').classList.add('hidden');
}
