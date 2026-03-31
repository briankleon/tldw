// ── STATE ─────────────────────────────────────────────────────────────
let currentData = null;

const LEVEL_COLORS = [
  '#d4410a', '#e8650d', '#f0920a', '#3a7fd4', '#1a5fb4',
  '#7a3aad', '#0a9460', '#8a6a10', '#6a3a0a'
];

// ── INIT ──────────────────────────────────────────────────────────────
document.getElementById('urlInput').addEventListener('keydown', e => {
  if (e.key === 'Enter') handleSubmit();
});

function tryExample(url) {
  document.getElementById('urlInput').value = url;
  handleSubmit();
}

function goHome() {
  show('landing');
  document.getElementById('urlInput').value = '';
  currentData = null;
}

function show(id) {
  ['landing', 'loading', 'result'].forEach(v => {
    document.getElementById(v).classList.toggle('hidden', v !== id);
  });
}

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
  }, 300);
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
