// Shared Chart.js helpers. Colors come from CSS tokens so light/dark both work.
const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

function applyChartDefaults() {
  Chart.defaults.font.family = 'system-ui, -apple-system, "Segoe UI", sans-serif';
  Chart.defaults.color = css('--text-secondary');
  Chart.defaults.borderColor = css('--grid');
  Chart.defaults.plugins.legend.labels.boxWidth = 12;
  Chart.defaults.plugins.tooltip.mode = 'index';
  Chart.defaults.plugins.tooltip.intersect = false;
  Chart.defaults.maintainAspectRatio = false;
  Chart.defaults.elements.bar.borderRadius = 4;
  Chart.defaults.elements.bar.borderSkipped = 'start';
  Chart.defaults.elements.line.borderWidth = 2;
  Chart.defaults.elements.point.radius = 4;
}

const SERIES = () => [css('--series-1'), css('--series-2'), css('--series-3')];
const SUBJECT_COLOR = () => ({ MAT: css('--series-1'), POR: css('--series-2') });
const SUBJECT_NAME = { MAT: 'Mathematics', POR: 'Portuguese' };

function axes(yTitle, extra = {}) {
  return {
    x: { grid: { display: false }, border: { color: css('--axis') } },
    y: { beginAtZero: true, title: { display: !!yTitle, text: yTitle },
         border: { display: false }, ...extra },
  };
}

function barChart(id, labels, data, yTitle, opts = {}) {
  const el = document.getElementById(id);
  if (!el) return;
  return new Chart(el, {
    type: 'bar',
    data: { labels, datasets: [{ label: yTitle, data, backgroundColor: opts.color || css('--series-1'),
            maxBarThickness: 42 }] },
    options: { indexAxis: opts.horizontal ? 'y' : 'x',
               plugins: { legend: { display: false } },
               scales: opts.horizontal
                 ? { x: { beginAtZero: true, title: { display: true, text: yTitle }, ...(opts.yScale || {}) },
                     y: { grid: { display: false } } }
                 : axes(yTitle, opts.yScale) },
  });
}

async function loadStats(subject) {
  const r = await fetch('/api/stats' + (subject ? `?subject=${subject}` : ''));
  return r.json();
}

function renderStatsCharts(s) {
  const charts = [];
  const pct = { min: 0, max: 100 };
  charts.push(barChart('gradeChart', s.grade_dist.labels.map(g => ({A:'A (16-20)',B:'B (14-15)',C:'C (12-13)',D:'D (10-11)',F:'F (0-9)'})[g]),
                       s.grade_dist.values, 'Students'));
  const codes = Object.keys(s.by_subject);
  const el = document.getElementById('periodChart');
  if (el) charts.push(new Chart(el, {
    type: 'bar',
    data: { labels: ['Period 1 (G1)', 'Period 2 (G2)', 'Final (G3)'],
            datasets: codes.map(c => ({ label: SUBJECT_NAME[c], backgroundColor: SUBJECT_COLOR()[c],
              data: ['G1', 'G2', 'G3'].map(k => s.by_subject[c][k]), maxBarThickness: 42 })) },
    options: { scales: axes('Average grade (0-20)', { max: 20 }) },
  }));
  charts.push(barChart('studyChart', s.studytime.labels, s.studytime.pass_rate, 'Pass rate (%)', { yScale: pct }));
  charts.push(barChart('failChart', s.failures.labels, s.failures.pass_rate, 'Pass rate (%)', { yScale: pct }));
  charts.push(barChart('absChart', s.absences.labels, s.absences.avg_g3, 'Average final grade', { yScale: { max: 20 } }));
  charts.push(barChart('walcChart', s.walc.labels, s.walc.avg_g3, 'Average final grade', { yScale: { max: 20 } }));
  charts.push(barChart('higherChart', s.higher.labels, s.higher.pass_rate, 'Pass rate (%)', { yScale: pct }));
  charts.push(barChart('corrChart', s.correlation.labels, s.correlation.values, 'Correlation with G3',
                       { horizontal: true, yScale: { beginAtZero: false, min: -1, max: 1 } }));

  const sc = document.getElementById('scatterChart');
  if (sc) charts.push(new Chart(sc, {
    type: 'scatter',
    data: { datasets: Object.entries(s.scatter).map(([c, pts]) => ({
      label: SUBJECT_NAME[c], data: pts.map(([x, y]) => ({ x, y })),
      backgroundColor: SUBJECT_COLOR()[c] + 'aa', borderColor: css('--surface-1'), borderWidth: 1, pointRadius: 4 })) },
    options: { plugins: { tooltip: { mode: 'nearest', intersect: true,
                 callbacks: { label: (c) => `${c.dataset.label}: G2 ${c.raw.x} → G3 ${c.raw.y}` } } },
               scales: { x: { title: { display: true, text: 'Period 2 grade (G2)' }, min: 0, max: 20 },
                         y: { title: { display: true, text: 'Final grade (G3)' }, min: 0, max: 20 } } },
  }));

  const rk = document.getElementById('riskChart');
  if (rk) {
    const total = s.risk.Low + s.risk.Medium + s.risk.High;
    if (!total) {
      rk.parentElement.innerHTML = '<p class="text-secondary text-center pt-5">No predictions yet. Use “Predict all”.</p>';
    } else {
      charts.push(new Chart(rk, {
        type: 'bar',
        data: { labels: ['Low risk', 'Medium risk', 'High risk'],
                datasets: [{ label: 'Students', data: [s.risk.Low, s.risk.Medium, s.risk.High],
                  backgroundColor: [css('--good'), css('--warning'), css('--critical')], maxBarThickness: 56 }] },
        options: { plugins: { legend: { display: false } }, scales: axes('Students') },
      }));
    }
  }
  return charts;
}

function setTheme(t) {
  document.documentElement.setAttribute('data-theme', t);
  document.documentElement.setAttribute('data-bs-theme', t);
  try { localStorage.setItem('spms-theme', t); } catch (e) {}
}
function toggleTheme() {
  const cur = document.documentElement.getAttribute('data-theme') ||
    (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
  setTheme(cur === 'dark' ? 'light' : 'dark');
  location.reload();
}
