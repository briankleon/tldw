// ── VISUAL ROUTER ─────────────────────────────────────────────────────
function renderVisual(type, content, container) {
  switch (type) {
    case 'hierarchy':   renderHierarchy(content, container); break;
    case 'timeline':    renderTimeline(content, container); break;
    case 'graph':       renderGraph(content, container); break;
    case 'comparison':  renderComparison(content, container); break;
    case 'stat_cards':  renderStatCards(content, container); break;
    default:            renderStatCards(content, container); break;
  }
}

// ── HIERARCHY ─────────────────────────────────────────────────────────
function renderHierarchy(content, container) {
  const levels = content.levels || [];

  const wrap = document.createElement('div');
  wrap.className = 'hierarchy-wrap';

  const title = document.createElement('div');
  title.style.cssText = `
    font-family: var(--font-display);
    font-size: 1.8rem;
    letter-spacing: 0.03em;
    margin-bottom: 1.5rem;
    color: var(--ink);
  `;
  title.textContent = content.title || 'Hierarchy';
  wrap.appendChild(title);

  levels.forEach((lvl, i) => {
    const color = LEVEL_COLORS[i % LEVEL_COLORS.length];
    const row = document.createElement('div');
    row.className = 'hierarchy-level';
    row.style.animationDelay = `${i * 0.08}s`;

    const num = document.createElement('div');
    num.className = 'hl-number';
    num.style.background = color;
    num.textContent = lvl.level ?? (i + 1);

    const content_div = document.createElement('div');
    content_div.className = 'hl-content';

    const name = document.createElement('div');
    name.className = 'hl-name';
    name.textContent = lvl.name || '';

    const desc = document.createElement('div');
    desc.className = 'hl-desc';
    desc.textContent = lvl.description || '';

    content_div.appendChild(name);
    content_div.appendChild(desc);

    if (lvl.traits && lvl.traits.length > 0) {
      const traits = document.createElement('div');
      traits.className = 'hl-traits';
      lvl.traits.forEach(t => {
        const tag = document.createElement('span');
        tag.className = 'hl-trait';
        tag.textContent = t;
        traits.appendChild(tag);
      });
      content_div.appendChild(traits);
    }

    row.appendChild(num);
    row.appendChild(content_div);
    wrap.appendChild(row);
  });

  container.appendChild(wrap);
}

// ── TIMELINE ──────────────────────────────────────────────────────────
function renderTimeline(content, container) {
  const steps = content.steps || [];

  const wrap = document.createElement('div');
  wrap.className = 'timeline-wrap';

  const title = document.createElement('div');
  title.style.cssText = `
    font-family: var(--font-display);
    font-size: 1.8rem;
    letter-spacing: 0.03em;
    margin-bottom: 1.5rem;
    color: var(--ink);
  `;
  title.textContent = content.title || 'Steps';
  wrap.appendChild(title);

  steps.forEach((step, i) => {
    const row = document.createElement('div');
    row.className = 'timeline-step';
    row.style.animationDelay = `${i * 0.1}s`;

    const num = document.createElement('div');
    num.className = 'ts-number';
    num.textContent = String(step.step ?? (i + 1)).padStart(2, '0');

    const contentDiv = document.createElement('div');
    contentDiv.className = 'ts-content';

    const stepTitle = document.createElement('div');
    stepTitle.className = 'ts-title';
    stepTitle.textContent = step.title || '';

    const desc = document.createElement('div');
    desc.className = 'ts-desc';
    desc.textContent = step.description || '';

    contentDiv.appendChild(stepTitle);
    contentDiv.appendChild(desc);

    if (step.tip) {
      const tip = document.createElement('div');
      tip.className = 'ts-tip';
      tip.textContent = '💡 ' + step.tip;
      contentDiv.appendChild(tip);
    }

    row.appendChild(num);
    row.appendChild(contentDiv);
    wrap.appendChild(row);
  });

  container.appendChild(wrap);
}

// ── COMPARISON ────────────────────────────────────────────────────────
function renderComparison(content, container) {
  const items = content.items || ['Option A', 'Option B'];
  const dimensions = content.dimensions || [];

  const wrap = document.createElement('div');
  wrap.className = 'comparison-wrap';

  const title = document.createElement('div');
  title.style.cssText = `
    font-family: var(--font-display);
    font-size: 1.8rem;
    letter-spacing: 0.03em;
    margin-bottom: 1.5rem;
    color: var(--ink);
  `;
  title.textContent = content.title || 'Comparison';
  wrap.appendChild(title);

  // Header row
  const header = document.createElement('div');
  header.className = 'comparison-header';
  header.innerHTML = `
    <div>Dimension</div>
    <div class="comp-item-a">${items[0] || 'Option A'}</div>
    <div class="comp-item-b">${items[1] || 'Option B'}</div>
  `;
  wrap.appendChild(header);

  // Dimension rows
  dimensions.forEach((dim, i) => {
    const row = document.createElement('div');
    row.className = 'comparison-row';
    row.style.animationDelay = `${i * 0.07}s`;

    const dimCell = document.createElement('div');
    dimCell.className = 'comp-dimension';
    dimCell.textContent = dim.dimension || '';

    const valA = document.createElement('div');
    valA.className = `comp-value${dim.winner === 0 ? ' winner' : ''}`;
    valA.innerHTML = `${dim.winner === 0 ? '<span class="winner-mark">✓</span>' : ''} ${dim.values?.[0] || '—'}`;

    const valB = document.createElement('div');
    valB.className = `comp-value${dim.winner === 1 ? ' winner' : ''}`;
    valB.innerHTML = `${dim.winner === 1 ? '<span class="winner-mark">✓</span>' : ''} ${dim.values?.[1] || '—'}`;

    row.appendChild(dimCell);
    row.appendChild(valA);
    row.appendChild(valB);
    wrap.appendChild(row);
  });

  // Verdict
  if (content.verdict) {
    const verdict = document.createElement('div');
    verdict.className = 'comparison-verdict';
    verdict.innerHTML = `<strong>Verdict:</strong> ${content.verdict}`;
    wrap.appendChild(verdict);
  }

  container.appendChild(wrap);
}

// ── STAT CARDS ────────────────────────────────────────────────────────
function renderStatCards(content, container) {
  const cards = content.cards || [];

  const title = document.createElement('div');
  title.style.cssText = `
    font-family: var(--font-display);
    font-size: 1.8rem;
    letter-spacing: 0.03em;
    margin-bottom: 1.5rem;
    color: var(--ink);
  `;
  title.textContent = content.title || 'Key Takeaways';
  container.appendChild(title);

  const wrap = document.createElement('div');
  wrap.className = 'stat-cards-wrap';

  cards.forEach((card, i) => {
    const el = document.createElement('div');
    el.className = 'stat-card';
    el.style.animationDelay = `${i * 0.07}s`;
    el.innerHTML = `
      <span class="sc-icon">${card.icon || '📌'}</span>
      <div class="sc-stat">${card.stat || ''}</div>
      <div class="sc-detail">${card.detail || ''}</div>
    `;
    wrap.appendChild(el);
  });

  container.appendChild(wrap);
}

// ── CONCEPT GRAPH (D3) ────────────────────────────────────────────────
function renderGraph(content, container) {
  const nodes = (content.nodes || []).map(n => ({ ...n }));
  const edges = (content.edges || []).filter(e => {
    const nodeIds = nodes.map(n => n.id);
    return nodeIds.includes(e.source) && nodeIds.includes(e.target);
  });

  const title = document.createElement('div');
  title.style.cssText = `
    font-family: var(--font-display);
    font-size: 1.8rem;
    letter-spacing: 0.03em;
    margin-bottom: 1.25rem;
    color: var(--ink);
  `;
  title.textContent = content.title || 'Concept Map';
  container.appendChild(title);

  const W = Math.min(container.clientWidth || 700, 860);
  const H = 500;

  const svg = d3.select(container)
    .append('svg')
    .attr('id', 'graphSvg')
    .attr('viewBox', `0 0 ${W} ${H}`)
    .attr('width', '100%')
    .attr('height', H);

  const g = svg.append('g');

  // Zoom
  svg.call(d3.zoom()
    .scaleExtent([0.4, 2.5])
    .on('zoom', e => g.attr('transform', e.transform))
  );

  // Unique groups → colour map
  const groups = [...new Set(nodes.map(n => n.group || 'default'))];
  const palette = ['#d4410a', '#1a6fd4', '#0a9460', '#7a3aad', '#8a6a10', '#3a7a9a'];
  const groupColor = {};
  groups.forEach((gr, i) => { groupColor[gr] = palette[i % palette.length]; });

  // Arrow marker
  svg.append('defs').append('marker')
    .attr('id', 'graphArrow')
    .attr('viewBox', '0 -5 10 10')
    .attr('refX', 26)
    .attr('refY', 0)
    .attr('markerWidth', 6)
    .attr('markerHeight', 6)
    .attr('orient', 'auto')
    .append('path')
    .attr('d', 'M0,-5L10,0L0,5')
    .attr('fill', '#ccc8be');

  // Links
  const link = g.append('g').selectAll('line')
    .data(edges)
    .enter().append('line')
    .attr('class', 'graph-link')
    .attr('marker-end', 'url(#graphArrow)');

  // Edge labels
  const linkLabel = g.append('g').selectAll('text')
    .data(edges.filter(e => e.label))
    .enter().append('text')
    .attr('class', 'graph-link-label')
    .text(d => d.label || '');

  // Nodes
  const node = g.append('g').selectAll('.graph-node')
    .data(nodes)
    .enter().append('g')
    .attr('class', 'graph-node')
    .call(d3.drag()
      .on('start', (e, d) => { if (!e.active) sim.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; })
      .on('drag', (e, d) => { d.fx = e.x; d.fy = e.y; })
      .on('end', (e, d) => { if (!e.active) sim.alphaTarget(0); d.fx = null; d.fy = null; })
    );

  node.append('circle')
    .attr('r', 20)
    .attr('fill', d => groupColor[d.group || 'default'] + '22')
    .attr('stroke', d => groupColor[d.group || 'default']);

  node.append('text')
    .attr('dy', 34)
    .text(d => d.label?.length > 16 ? d.label.slice(0, 14) + '…' : d.label);

  node.append('title').text(d => `${d.label}\n${d.description || ''}`);

  // Legend
  const legendG = svg.append('g').attr('transform', `translate(12, 12)`);
  groups.forEach((gr, i) => {
    const row = legendG.append('g').attr('transform', `translate(0, ${i * 18})`);
    row.append('circle').attr('r', 5).attr('cx', 5).attr('cy', 5)
      .attr('fill', groupColor[gr] + '44').attr('stroke', groupColor[gr]).attr('stroke-width', 1.5);
    row.append('text')
      .attr('x', 14).attr('y', 9)
      .attr('font-family', 'JetBrains Mono, monospace')
      .attr('font-size', 9)
      .attr('fill', '#7a7060')
      .text(gr);
  });

  // Simulation
  const sim = d3.forceSimulation(nodes)
    .force('link', d3.forceLink(edges).id(d => d.id).distance(130).strength(0.5))
    .force('charge', d3.forceManyBody().strength(-350))
    .force('center', d3.forceCenter(W / 2, H / 2))
    .force('collision', d3.forceCollide(42))
    .on('tick', () => {
      link
        .attr('x1', d => d.source.x).attr('y1', d => d.source.y)
        .attr('x2', d => d.target.x).attr('y2', d => d.target.y);

      linkLabel
        .attr('x', d => (d.source.x + d.target.x) / 2)
        .attr('y', d => (d.source.y + d.target.y) / 2);

      node.attr('transform', d => `translate(${d.x},${d.y})`);
    });
}
