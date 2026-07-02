# ruff: noqa: E501
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["dashboard"])


@router.get("/news-sources", response_class=HTMLResponse)
async def news_sources_dashboard() -> str:
    return """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>News Sources · News Intelligence Platform</title>
  <style>
    :root { color-scheme: dark; font-family: Inter, Segoe UI, system-ui, sans-serif; }
    body { margin: 0; background: #0b1020; color: #eef2ff; }
    header { padding: 28px 32px; background: linear-gradient(135deg, #111a35, #182451); }
    main { padding: 24px 32px 48px; display: grid; gap: 24px; }
    h1, h2 { margin: 0 0 12px; }
    p { color: #b9c2df; }
    .card { background: #11182e; border: 1px solid #263250; border-radius: 16px; padding: 20px; box-shadow: 0 16px 50px rgba(0,0,0,.22); }
    .grid { display: grid; grid-template-columns: repeat(5, minmax(160px, 1fr)); gap: 12px; align-items: end; }
    label { display: grid; gap: 6px; color: #b9c2df; font-size: 13px; }
    input, select, textarea { width: 100%; box-sizing: border-box; border: 1px solid #33415f; border-radius: 10px; padding: 10px 12px; background: #0d1428; color: #eef2ff; }
    textarea { min-height: 42px; resize: vertical; }
    button { border: 0; border-radius: 10px; padding: 10px 14px; background: #5b7cfa; color: white; font-weight: 700; cursor: pointer; }
    button.secondary { background: #263250; }
    button.danger { background: #b42342; }
    button:disabled { opacity: .5; cursor: not-allowed; }
    table { width: 100%; border-collapse: collapse; overflow: hidden; }
    th, td { border-bottom: 1px solid #263250; padding: 10px 8px; text-align: left; vertical-align: top; font-size: 13px; }
    th { color: #aebaf0; font-size: 12px; text-transform: uppercase; letter-spacing: .06em; }
    .actions { display: flex; gap: 8px; flex-wrap: wrap; }
    .status { display: inline-flex; padding: 4px 8px; border-radius: 999px; background: #1b2748; color: #cdd7ff; }
    .ok { background: #123c2b; color: #b7f7d4; }
    .warn { background: #493915; color: #ffe6a8; }
    .error { background: #451b29; color: #ffc2d0; }
    .toolbar { display: flex; justify-content: space-between; gap: 12px; align-items: center; flex-wrap: wrap; }
    .progress-grid { display: grid; grid-template-columns: repeat(6, minmax(120px, 1fr)); gap: 12px; }
    .metric { background: #0d1428; border-radius: 12px; padding: 12px; border: 1px solid #263250; }
    .metric b { display: block; font-size: 22px; margin-top: 4px; }
    .muted { color: #94a0c5; font-size: 12px; }
    .article-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 14px; }
    .article-card { background: #0d1428; border: 1px solid #263250; border-radius: 14px; padding: 14px; display: grid; gap: 10px; }
    .article-card h3 { margin: 0; font-size: 16px; line-height: 1.35; }
    .pill-row { display: flex; gap: 6px; flex-wrap: wrap; }
    .pill { border-radius: 999px; background: #1b2748; color: #cdd7ff; padding: 3px 8px; font-size: 11px; }
    .pill.good { background: #123c2b; color: #b7f7d4; }
    .pill.warn { background: #493915; color: #ffe6a8; }
    a { color: #9eb3ff; text-decoration: none; }
    a:hover { text-decoration: underline; }
  </style>
</head>
<body>
  <header>
    <h1>News Sources</h1>
    <p>Add a publisher by homepage URL. The backend discovers RSS, Atom, robots.txt sitemaps, and common feed/sitemap paths automatically.</p>
  </header>
  <main>
    <section class="card">
      <div class="toolbar">
        <h2>Add News Source</h2>
        <label style="max-width: 260px">Internal token
          <input id="token" type="password" value="dev-internal-token" />
        </label>
      </div>
      <div class="grid">
        <label>Publisher name <input id="publisherName" placeholder="BBC News" /></label>
        <label>Website URL <input id="websiteUrl" placeholder="https://www.bbc.com/news" /></label>
        <label>Fetch frequency
          <select id="fetchFrequency">
            <option value="manual">Manual</option>
            <option value="every_15_minutes">Every 15 Minutes</option>
            <option value="hourly" selected>Hourly</option>
            <option value="every_6_hours">Every 6 Hours</option>
            <option value="daily">Daily</option>
          </select>
        </label>
        <label>Manual RSS/sitemap fallback <textarea id="manualEndpoints" placeholder="One URL per line"></textarea></label>
        <button onclick="discoverAndAdd()">Discover and Add</button>
      </div>
      <p id="addStatus" class="muted"></p>
    </section>

    <section class="card">
      <div class="toolbar">
        <h2>Sources</h2>
        <div class="actions">
          <button onclick="fetchAll()">Fetch All News</button>
          <button class="secondary" onclick="loadSources()">Refresh</button>
        </div>
      </div>
      <div style="overflow:auto">
        <table>
          <thead>
            <tr>
              <th>Publisher</th><th>Website</th><th>Discovery</th><th>RSS</th><th>Sitemaps</th>
              <th>Last fetched</th><th>Frequency</th><th>Discovered</th><th>Extracted</th>
              <th>Duplicates</th><th>Failed</th><th>Status</th><th>Actions</th>
            </tr>
          </thead>
          <tbody id="sourcesBody"></tbody>
        </table>
      </div>
    </section>

    <section class="card">
      <h2>Fetch Progress</h2>
      <p id="jobLine" class="muted">No fetch job selected yet.</p>
      <div class="progress-grid">
        <div class="metric">Publishers processed <b id="mPublishers">0</b></div>
        <div class="metric">URLs discovered <b id="mUrls">0</b></div>
        <div class="metric">Articles queued <b id="mQueued">0</b></div>
        <div class="metric">Articles extracted <b id="mExtracted">0</b></div>
        <div class="metric">Duplicates skipped <b id="mDuplicates">0</b></div>
        <div class="metric">Failed extractions <b id="mFailed">0</b></div>
      </div>
    </section>

    <section class="card">
      <div class="toolbar">
        <h2>Extracted News</h2>
        <button class="secondary" onclick="loadArticles()">Refresh Articles</button>
      </div>
      <div id="articleGrid" class="article-grid"></div>
    </section>
  </main>
  <script>
    let currentJobId = null;
    let pollHandle = null;

    function tokenHeaders() {
      return { 'Content-Type': 'application/json', 'X-Internal-Token': document.getElementById('token').value };
    }
    function fmtDate(value) { return value ? new Date(value).toLocaleString() : '—'; }
    function fmtQuality(value) { return value === null || value === undefined ? '—' : Math.round(value * 100) + '%'; }
    function qualityClass(value) { return value !== null && value !== undefined && value >= 0.65 ? 'good' : 'warn'; }
    function warningPills(warnings) {
      if (!warnings || !warnings.length) return '<span class="pill good">no warnings</span>';
      return warnings.slice(0, 3).map(warning => `<span class="pill warn">${warning}</span>`).join('');
    }
    function badge(value) {
      const cls = value === 'ready' || value === 'active' ? 'ok' : (value === 'failed' ? 'error' : 'warn');
      return `<span class="status ${cls}">${value || 'unknown'}</span>`;
    }
    async function api(path, options = {}) {
      const res = await fetch(path, options);
      if (!res.ok) {
        let detail = await res.text();
        try { detail = JSON.parse(detail).detail || detail; } catch {}
        throw new Error(detail);
      }
      if (res.status === 204) return null;
      return await res.json();
    }
    async function discoverAndAdd() {
      const status = document.getElementById('addStatus');
      status.textContent = 'Discovering feeds and sitemaps…';
      const manual = document.getElementById('manualEndpoints').value.split('\\n').map(x => x.trim()).filter(Boolean);
      try {
        const result = await api('/api/v1/publishers/discover', {
          method: 'POST',
          headers: tokenHeaders(),
          body: JSON.stringify({
            publisher_name: document.getElementById('publisherName').value,
            website_url: document.getElementById('websiteUrl').value,
            fetch_frequency: document.getElementById('fetchFrequency').value,
            manual_endpoints: manual
          })
        });
        status.textContent = `Added ${result.publisher.name}. Valid channels: ${result.valid_endpoint_count}.`;
        await loadSources();
      } catch (err) {
        status.textContent = `Failed: ${err.message}`;
      }
    }
    async function loadSources() {
      const sources = await api('/api/v1/publishers');
      document.getElementById('sourcesBody').innerHTML = sources.map(source => `
        <tr>
          <td>${source.name}<div class="muted">${source.canonical_domain}</div></td>
          <td>${source.homepage_url ? `<a href="${source.homepage_url}" target="_blank">${source.homepage_url}</a>` : '—'}</td>
          <td>${badge(source.discovery_status)}<div class="muted">${source.discovery_message || ''}</div></td>
          <td>${source.rss_feed_count}</td><td>${source.sitemap_count}</td>
          <td>${fmtDate(source.last_fetched_at)}</td><td>${source.fetch_frequency}</td>
          <td>${source.articles_discovered}</td><td>${source.articles_extracted}</td>
          <td>${source.duplicates_skipped}</td><td>${source.failed_articles}</td>
          <td>${badge(source.current_status)}</td>
          <td class="actions">
            <button onclick="fetchPublisher('${source.id}')">Fetch</button>
            <button class="secondary" onclick="fetchPublisher('${source.id}')">Retry</button>
            <button class="secondary" onclick="prefill('${source.name}', '${source.homepage_url || ''}', '${source.fetch_frequency}')">Edit</button>
            <button class="danger" onclick="deletePublisher('${source.id}')">Delete</button>
          </td>
        </tr>
      `).join('');
    }
    async function loadArticles() {
      const articles = await api('/api/v1/articles?limit=24');
      document.getElementById('articleGrid').innerHTML = articles.length ? articles.map(article => `
        <article class="article-card">
          <h3><a href="${article.canonical_url}" target="_blank">${article.title}</a></h3>
          <div class="muted">Published: ${fmtDate(article.published_at)} · Observed: ${fmtDate(article.first_observed_at)}</div>
          <div class="muted">Words: ${article.word_count || '—'} · Method: ${article.latest_extraction_method || '—'} · Quality: ${fmtQuality(article.latest_extraction_quality_score)}</div>
          <div class="pill-row"><span class="pill ${qualityClass(article.latest_extraction_quality_score)}">quality ${fmtQuality(article.latest_extraction_quality_score)}</span>${warningPills(article.latest_extraction_warnings)}</div>
          <div class="muted">Event: <a href="/api/v1/events/${article.event_id}" target="_blank">${article.event_id.slice(0, 8)}</a></div>
          <div class="actions">
            <a href="/api/v1/articles/${article.id}" target="_blank">Article JSON</a>
            <a href="/api/v1/articles/${article.id}/claims" target="_blank">Claims</a>
          </div>
        </article>
      `).join('') : '<p class="muted">No extracted articles yet. Add a source, click Fetch, and keep the poller/article worker running.</p>';
    }
    function prefill(name, url, frequency) {
      document.getElementById('publisherName').value = name;
      document.getElementById('websiteUrl').value = url;
      document.getElementById('fetchFrequency').value = frequency;
      document.getElementById('addStatus').textContent = 'Edit currently pre-fills the form; delete and re-add to change stored endpoints.';
    }
    async function fetchPublisher(id) {
      const result = await api(`/api/v1/publishers/${id}/fetch`, { method: 'POST', headers: tokenHeaders() });
      watchJob(result.job_id);
      await loadSources();
    }
    async function fetchAll() {
      const result = await api('/api/v1/fetch/all', { method: 'POST', headers: tokenHeaders() });
      watchJob(result.job_id);
      await loadSources();
    }
    async function deletePublisher(id) {
      if (!confirm('Disable this publisher and its discovery channels?')) return;
      await api(`/api/v1/publishers/${id}`, { method: 'DELETE', headers: tokenHeaders() });
      await loadSources();
    }
    function watchJob(jobId) {
      currentJobId = jobId;
      if (pollHandle) clearInterval(pollHandle);
      pollJob();
      pollHandle = setInterval(pollJob, 2500);
    }
    async function pollJob() {
      if (!currentJobId) return;
      const job = await api(`/api/v1/fetch-jobs/${currentJobId}`);
      document.getElementById('jobLine').textContent = `Job ${job.id} · ${job.status} · ${job.message || ''}`;
      document.getElementById('mPublishers').textContent = `${job.publishers_processed}/${job.publishers_total}`;
      document.getElementById('mUrls').textContent = job.urls_discovered;
      document.getElementById('mQueued').textContent = job.articles_queued;
      document.getElementById('mExtracted').textContent = job.articles_extracted;
      document.getElementById('mDuplicates').textContent = job.duplicates_skipped;
      document.getElementById('mFailed').textContent = job.failed_articles;
      loadArticles().catch(console.error);
    }
    loadSources().catch(console.error);
    loadArticles().catch(console.error);
  </script>
</body>
</html>
"""
