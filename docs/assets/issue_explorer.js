(function () {
  'use strict';
  var dataNode = document.getElementById('issue-explorer-data');
  if (!dataNode) return;
  var payload = JSON.parse(dataNode.textContent), rows = payload.rows;
  var el = function (id) { return document.getElementById('issue-' + id); };
  var escape = function (value) { var span = document.createElement('span'); span.textContent = String(value); return span.innerHTML; };
  var palette = ['#285f91', '#bd5d36', '#35827b', '#8a649d', '#a17b23', '#527499', '#8b929b'];
  var bands = ['≤7 分', '7–9 分（不含7）', '>9 分', '未评分'];
  var bandColors = ['#b8cbdc', '#3f80b3', '#b75a35', '#999999'];
  var bins = Array.from({length: 10}, function (_, i) { return i + '–' + (i + 1) + (i === 9 ? '（含10）' : ''); }).concat(['未评分']);
  var binOf = function (r) { return r.score === null ? 10 : Math.min(9, Math.floor(r.score)); };
  var bandOf = function (r) { return r.score === null ? 3 : r.score > 9 ? 2 : r.score > 7 ? 1 : 0; };
  var state = {field: '', bin: null, band: null, group: null, tag: '', query: '', page: 0};
  var scoreChart, fieldChart, base = [], fields = [], leading = [];
  var normalize = function (text) { return text.trim().replace(/\s+/g, ' ').toLowerCase(); };
  var cards = new Map();
  document.querySelectorAll('.article-card').forEach(function (card) { cards.set(normalize(card.dataset.favoriteTitle || ''), card); });
  rows.forEach(function (row, index) {
    var card = cards.get(normalize(row.title));
    if (card) {
      var anchor = document.createElement('span'); anchor.id = 'issue-body-' + index; anchor.className = 'issue-body-anchor';
      card.prepend(anchor); row.anchor = anchor.id;
    }
    // Keep only navigable public article URLs, including historical local-data oddities.
    if (!/^https?:\/\//i.test(row.url || '')) row.url = '';
  });
  function counts(values, key) {
    var result = new Map();
    values.forEach(function (r) { var k = key(r); result.set(k, (result.get(k) || 0) + 1); });
    return Array.from(result).sort(function (a, b) { return b[1] - a[1] || a[0].localeCompare(b[0], 'zh'); });
  }
  function fieldGroup(row) { return leading.includes(row.field) ? row.field : '其他领域'; }
  function resetFilters() {
    Object.assign(state, {field: '', bin: null, band: null, group: null, tag: '', query: '', page: 0});
    el('field').value = ''; el('score').value = ''; el('query').value = '';
    renderResults(); renderTopics();
  }
  function matches(row) {
    return (!state.field || row.field === state.field) &&
      (state.bin === null || binOf(row) === state.bin) &&
      (state.band === null || bandOf(row) === state.band) &&
      (!state.group || fieldGroup(row) === state.group) &&
      (!state.tag || row.tags.includes(state.tag)) &&
      (!state.query || [row.title, row.titleZh, row.summary, row.tags.join(' ')].join(' ').toLowerCase().includes(state.query));
  }
  function renderResults() {
    var selected = base.filter(matches).sort(function (a, b) { return (b.score === null ? -1 : b.score) - (a.score === null ? -1 : a.score) || a.title.localeCompare(b.title); });
    var pageCount = Math.max(1, Math.ceil(selected.length / 8));
    state.page = Math.min(state.page, pageCount - 1);
    el('result-count').textContent = selected.length + ' / ' + base.length + ' 篇';
    var filters = [state.field || state.group, state.bin === null ? '' : bins[state.bin] + ' 分', state.band === null ? '' : bands[state.band], state.tag, state.query ? '搜索：' + state.query : ''].filter(Boolean);
    if (filters.length) el('reading-results').open = true;
    el('status').textContent = filters.length ? '已选：' + filters.join(' · ') : '点击图表，找到你想读的文章';
    var list = el('result-list'); list.replaceChildren();
    if (!selected.length) { var empty = document.createElement('p'); empty.textContent = '没有符合条件的文章，可以清除筛选后重试。'; list.append(empty); }
    selected.slice(state.page * 8, state.page * 8 + 8).forEach(function (r) {
      var item = document.createElement('div'); item.className = 'issue-result-item';
      var link = document.createElement('a'); link.textContent = r.titleZh;
      if (r.anchor) link.href = '#' + r.anchor;
      else if (r.url) { link.href = r.url; link.target = '_blank'; link.rel = 'noopener noreferrer'; }
      item.append(link);
      var meta = document.createElement('div'); meta.className = 'issue-result-meta';
      meta.textContent = (r.score === null ? '未评分' : r.score.toFixed(1) + ' 分') + ' · ' + r.field + ' · ' + r.tier + ' · ' + (r.anchor ? '查看正文 ↓' : '本期未展开 · 查看原文 ↗');
      item.append(meta);
      if (r.summary) { var summary = document.createElement('p'); summary.textContent = r.summary.length > 135 ? r.summary.slice(0, 135) + '…' : r.summary; item.append(summary); }
      list.append(item);
    });
    el('page').textContent = (state.page + 1) + ' / ' + pageCount;
    el('prev').disabled = state.page === 0; el('next').disabled = state.page + 1 >= pageCount;
    document.querySelectorAll('#issue-topic-cloud button').forEach(function (button) { button.setAttribute('aria-pressed', String(button.dataset.tag === state.tag)); });
  }
  function renderTopics() {
    var tally = new Map();
    base.forEach(function (r) { r.tags.forEach(function (tag) { tally.set(tag, (tally.get(tag) || 0) + 1); }); });
    var tags = Array.from(tally).sort(function (a, b) { return b[1] - a[1] || a[0].localeCompare(b[0], 'zh'); }).slice(0, 26);
    var cloud = el('topic-cloud'); cloud.replaceChildren();
    if (!tags.length) { cloud.textContent = '本期没有可用的主题标签。'; return; }
    var low = tags[tags.length - 1][1], high = tags[0][1];
    // A deterministic, horizontal cloud keeps Chinese text legible and keyboard accessible.
    tags.sort(function (a, b) { return a[0].localeCompare(b[0], 'zh'); }).forEach(function (entry, i) {
      var button = document.createElement('button'); button.type = 'button'; button.dataset.tag = entry[0];
      button.textContent = entry[0]; button.title = entry[0] + ' · ' + entry[1] + ' 篇';
      button.setAttribute('aria-label', entry[0] + '，' + entry[1] + ' 篇，点击筛选');
      button.setAttribute('aria-pressed', String(state.tag === entry[0]));
      button.style.fontSize = (15 + (high === low ? 8 : (entry[1] - low) / (high - low) * 18)) + 'px';
      button.style.color = palette[i % 5];
      button.addEventListener('click', function () { state.tag = state.tag === entry[0] ? '' : entry[0]; state.page = 0; renderResults(); });
      cloud.append(button);
    });
  }
  function renderTable() {
    var table = '<table><thead><tr><th>主领域</th>' + bands.map(function (b) { return '<th>' + escape(b) + '</th>'; }).join('') + '<th>合计</th></tr></thead><tbody>';
    fields.forEach(function (f) { var group = base.filter(function (r) { return r.field === f[0]; }); table += '<tr><td>' + escape(f[0]) + '</td>' + bands.map(function (_, i) { return '<td>' + group.filter(function (r) { return bandOf(r) === i; }).length + '</td>'; }).join('') + '<td>' + f[1] + '</td></tr>'; });
    table += '<tr><th>合计</th>' + bands.map(function (_, i) { return '<td>' + base.filter(function (r) { return bandOf(r) === i; }).length + '</td>'; }).join('') + '<td>' + base.length + '</td></tr></tbody></table>';
    table += '<table><thead><tr><th>评分区间</th><th>篇数</th></tr></thead><tbody>' + bins.map(function (label, i) { return '<tr><td>' + label + '</td><td>' + base.filter(function (r) { return binOf(r) === i; }).length + '</td></tr>'; }).join('') + '</tbody></table>';
    el('data-table').innerHTML = table;
  }
  function drawCharts() {
    if (!window.echarts) { el('score-chart').textContent = '图表未加载，请查看统计明细；文章筛选仍可使用。'; el('field-chart').textContent = '研究领域和评分明细见下方。'; return; }
    if (!scoreChart) {
      scoreChart = echarts.init(el('score-chart'), null, {renderer: 'svg'});
      fieldChart = echarts.init(el('field-chart'), null, {renderer: 'svg'});
      scoreChart.on('click', function (p) {
        if (p.componentType !== 'series' || !p.value) return;
        state.field = ''; state.band = null; state.group = p.seriesName; state.bin = p.dataIndex; state.page = 0;
        el('field').value = ''; el('score').value = 'bin:' + state.bin; renderResults();
      });
      fieldChart.on('click', function (p) {
        if (p.componentType !== 'series' || !p.value) return;
        state.field = p.name; state.group = null; state.bin = null; state.band = bands.indexOf(p.seriesName); state.page = 0;
        el('field').value = state.field; el('score').value = 'band:' + state.band; renderResults();
      });
      new ResizeObserver(function () { scoreChart.resize(); fieldChart.resize(); }).observe(el('explorer'));
    }
    var groups = leading.concat(fields.length > leading.length ? ['其他领域'] : []);
    var shownBins = base.some(function (r) { return r.score === null; }) ? bins : bins.slice(0, 10);
    var tip = {trigger: 'axis', confine: true, formatter: function (params) {
      var nonzero = params.filter(function (p) { return p.value > 0; });
      var total = nonzero.reduce(function (sum, p) { return sum + p.value; }, 0);
      return escape(params[0].axisValueLabel) + '<br>' + nonzero.map(function (p) { return p.marker + escape(p.seriesName) + '：' + p.value + ' 篇'; }).join('<br>') + '<br>合计 ' + total + ' 篇 · 占当前范围 ' + (base.length ? total / base.length * 100 : 0).toFixed(1) + '%';
    }};
    scoreChart.setOption({animation: false, color: palette, textStyle: {fontFamily: 'Microsoft YaHei, sans-serif', fontSize: 12}, aria: {enabled: true},
      tooltip: tip, legend: {bottom: 0, itemWidth: 13, itemGap: 10, textStyle: {fontSize: 12}, selectedMode: false, formatter: function (name) { return name.replace('神经科学', '').replace('（未分领域）', ''); }},
      grid: {left: 38, right: 12, top: 24, bottom: 105},
      xAxis: {type: 'category', data: shownBins.map(function (_, i) { return i === 10 ? '未评分' : i + '–' + (i + 1); }), axisLabel: {interval: 0, rotate: 40, fontSize: 12}},
      yAxis: {type: 'value', name: '篇数', minInterval: 1},
      series: groups.map(function (field) { return {name: field, type: 'bar', stack: 'papers', barCategoryGap: '12%', emphasis: {focus: 'series'}, data: shownBins.map(function (_, i) { return base.filter(function (r) { return fieldGroup(r) === field && binOf(r) === i; }).length; })}; })
    }, true);
    el('field-chart').style.height = Math.max(440, fields.length * 32 + 100) + 'px'; fieldChart.resize();
    fieldChart.setOption({animation: false, color: bandColors, textStyle: {fontFamily: 'Microsoft YaHei, sans-serif', fontSize: 12}, aria: {enabled: true},
      tooltip: tip, legend: {bottom: 0, textStyle: {fontSize: 12}, selectedMode: false}, grid: {left: 150, right: 12, top: 24, bottom: 78},
      xAxis: {type: 'value', name: '篇数', nameLocation: 'middle', nameGap: 28, minInterval: 1},
      yAxis: {type: 'category', inverse: true, data: fields.map(function (f) { return f[0]; }), axisLabel: {fontSize: 12, width: 138, overflow: 'break', interval: 0}},
      series: bands.map(function (band, index) { return {name: band, type: 'bar', stack: 'papers', barMaxWidth: 22, label: {show: true, fontSize: 10, color: index === 0 ? '#203e58' : '#ffffff', formatter: function (p) { return p.value >= 8 ? p.value : ''; }}, data: fields.map(function (f) { return base.filter(function (r) { return r.field === f[0] && bandOf(r) === index; }).length; })}; })
    }, true);
  }
  function setScope() {
    base = rows.filter(function (r) { return el('scope').value === 'all' || r.expanded; });
    fields = counts(base, function (r) { return r.field; }); leading = counts(rows, function (r) { return r.field; }).slice(0, 6).map(function (f) { return f[0]; });
    el('field').replaceChildren(new Option('全部领域', ''));
    fields.forEach(function (f) { el('field').append(new Option(f[0] + '（' + f[1] + '）', f[0])); });
    resetFilters(); drawCharts(); renderTable();
  }
  bins.forEach(function (bin, i) { el('score').append(new Option(bin + (i === 10 ? '' : ' 分'), 'bin:' + i)); });
  bands.forEach(function (band, i) { el('score').append(new Option(band, 'band:' + i)); });
  el('scope').addEventListener('change', setScope);
  document.querySelector('.issue-heading a').addEventListener('click', function () { el('reading-results').open = true; });
  el('reset').addEventListener('click', resetFilters);
  el('field').addEventListener('change', function () { state.field = this.value; state.group = null; state.page = 0; renderResults(); });
  el('score').addEventListener('change', function () { var pair = this.value.split(':'); state.bin = pair[0] === 'bin' ? Number(pair[1]) : null; state.band = pair[0] === 'band' ? Number(pair[1]) : null; state.page = 0; renderResults(); });
  el('query').addEventListener('input', function () { state.query = this.value.trim().toLowerCase(); state.page = 0; renderResults(); });
  el('prev').addEventListener('click', function () { state.page--; renderResults(); el('reading-results').scrollIntoView({block: 'start'}); });
  el('next').addEventListener('click', function () { state.page++; renderResults(); el('reading-results').scrollIntoView({block: 'start'}); });
  setScope();
})();
