"""Dashboard 可视化页面生成模块。

使用 sql.js 在浏览器中加载精简版 SQLite 数据库，
通过 ECharts 渲染交互式数据可视化图表。
"""
from __future__ import annotations

from pathlib import Path

from .page import render_page


def render_dashboard_page(output_dir: Path) -> None:
    """生成 docs/dashboard.html。"""
    body = _BODY_HTML
    html_content = render_page("数据统计 Dashboard", body)
    # 在 </head> 前注入 dashboard 专属样式
    html_content = html_content.replace("</head>", _DASHBOARD_STYLE + "\n</head>")
    # 在 </body> 前插入 dashboard 脚本
    html_content = html_content.replace("</body>", _DASHBOARD_SCRIPT + "\n</body>")
    (output_dir / "dashboard.html").write_text(html_content, encoding="utf-8")


_BODY_HTML = """
<h1>数据统计 Dashboard</h1>

<div id="db-loading">
  <p class="meta">正在加载数据库（约 3MB），请稍候...</p>
  <div class="loading-spinner"></div>
</div>

<div id="db-error" hidden>
  <p class="meta" style="color:#c0392b">数据库加载失败，请刷新重试。</p>
</div>

<div id="dashboard-controls" hidden>
  <div class="control-row">
    <label>日期范围：</label>
    <input type="date" id="date-start" class="date-input">
    <span>至</span>
    <input type="date" id="date-end" class="date-input">
    <button class="ctrl-btn" id="btn-all-dates">全部</button>
    <button class="ctrl-btn" id="btn-recent-4w">最近4周</button>
  </div>
  <div class="control-row">
    <label>领域筛选：</label>
    <span id="field-checkboxes"></span>
    <button class="ctrl-btn" id="btn-all-fields">全选</button>
    <button class="ctrl-btn" id="btn-no-fields">清除</button>
  </div>
  <div class="control-row">
    <label>归一化模式：</label>
    <select id="normalize-mode" class="date-input">
      <option value="absolute">绝对数量</option>
      <option value="contribution">贡献度（列归一化）</option>
      <option value="focus">专注度（行归一化）</option>
    </select>
  </div>
</div>

<div id="dashboard-charts" hidden>
  <div class="chart-grid">
    <div class="chart-card" id="card-country-heatmap">
      <div class="card-header">
        <h3>国家/地区发文量热力图</h3>
        <button class="card-expand-btn" onclick="toggleExpand(this)">⤢</button>
      </div>
      <div id="chart-country-heatmap" class="chart-container"></div>
    </div>
    <div class="chart-card" id="card-country-score">
      <div class="card-header">
        <h3>国家/地区平均评分</h3>
        <button class="card-expand-btn" onclick="toggleExpand(this)">⤢</button>
      </div>
      <div id="chart-country-score" class="chart-container"></div>
    </div>
    <div class="chart-card" id="card-field-radar">
      <div class="card-header">
        <h3>研究领域分布</h3>
        <button class="card-expand-btn" onclick="toggleExpand(this)">⤢</button>
      </div>
      <div class="chart-controls">
        <select id="radar-mode" class="date-input">
          <option value="overall">整体分布</option>
          <option value="country">国家/地区对比</option>
        </select>
        <select id="radar-normalize" class="date-input">
          <option value="absolute">绝对数量</option>
          <option value="contribution">贡献比例</option>
          <option value="focus">国家/地区中心归一化</option>
        </select>
        <div id="radar-country-select" hidden></div>
      </div>
      <div id="chart-field-radar" class="chart-container"></div>
    </div>
    <div class="chart-card" id="card-score-radar">
      <div class="card-header">
        <h3>国家/地区评分领域分布</h3>
        <button class="card-expand-btn" onclick="toggleExpand(this)">⤢</button>
      </div>
      <div class="chart-controls">
        <select id="score-radar-mode" class="date-input">
          <option value="overall">整体分布</option>
          <option value="country">国家/地区对比</option>
        </select>
        <div id="score-radar-country-select" hidden></div>
      </div>
      <div id="chart-score-radar" class="chart-container"></div>
    </div>
    <div class="chart-card" id="card-institution-scatter">
      <div class="card-header">
        <h3>机构排名（发文量 × 评分）</h3>
        <button class="card-expand-btn" onclick="toggleExpand(this)">⤢</button>
      </div>
      <div id="chart-institution-scatter" class="chart-container"></div>
    </div>
    <div class="chart-card" id="card-wordcloud">
      <div class="card-header">
        <h3>交叉标签词云</h3>
        <button class="card-expand-btn" onclick="toggleExpand(this)">⤢</button>
      </div>
      <div class="chart-controls">
        <select id="wordcloud-country" class="date-input">
          <option value="">全部国家/地区</option>
        </select>
        <select id="wordcloud-style" class="date-input">
          <option value="blue">蓝色渐变</option>
          <option value="rainbow">彩虹色</option>
          <option value="warm">暖色调</option>
          <option value="cool">冷色调</option>
          <option value="red">红色渐变</option>
          <option value="green">绿色渐变</option>
          <option value="purple">紫色渐变</option>
        </select>
      </div>
      <div id="chart-wordcloud" class="chart-container"></div>
    </div>
    <div class="chart-card chart-wide" id="card-country-field">
      <div class="card-header">
        <h3>国家/地区 × 领域交叉热力图</h3>
        <button class="card-expand-btn" onclick="toggleExpand(this)">⤢</button>
      </div>
      <div id="chart-country-field" class="chart-container"></div>
    </div>
    <div class="chart-card" id="card-score-dist">
      <div class="card-header">
        <h3>评分分布</h3>
        <button class="card-expand-btn" onclick="toggleExpand(this)">⤢</button>
      </div>
      <div id="chart-score-dist" class="chart-container"></div>
    </div>
    <div class="chart-card" id="card-time-trend">
      <div class="card-header">
        <h3>时间趋势</h3>
        <button class="card-expand-btn" onclick="toggleExpand(this)">⤢</button>
      </div>
      <div class="chart-controls">
        <button class="ctrl-btn trend-mode active" data-mode="week">按周</button>
        <button class="ctrl-btn trend-mode" data-mode="day">按天</button>
        <label style="margin-left:12px"><input type="checkbox" id="trend-smooth"> 平滑</label>
      </div>
      <div id="chart-time-trend" class="chart-container"></div>
    </div>
    <div class="chart-card" id="card-field-trend">
      <div class="card-header">
        <h3>领域时间趋势</h3>
        <button class="card-expand-btn" onclick="toggleExpand(this)">⤢</button>
      </div>
      <div class="chart-controls">
        <button class="ctrl-btn field-trend-mode active" data-mode="week">按周</button>
        <button class="ctrl-btn field-trend-mode" data-mode="day">按天</button>
      </div>
      <div id="chart-field-trend" class="chart-container"></div>
    </div>
    <div class="chart-card" id="card-country-trend">
      <div class="card-header">
        <h3>国家/地区发文趋势</h3>
        <button class="card-expand-btn" onclick="toggleExpand(this)">⤢</button>
      </div>
      <div class="chart-controls">
        <button class="ctrl-btn country-trend-mode active" data-mode="week">按周</button>
        <button class="ctrl-btn country-trend-mode" data-mode="day">按天</button>
      </div>
      <div id="chart-country-trend" class="chart-container"></div>
    </div>
    <div class="chart-card" id="card-journal-bar">
      <div class="card-header">
        <h3>期刊发文量 TOP20</h3>
        <button class="card-expand-btn" onclick="toggleExpand(this)">⤢</button>
      </div>
      <div id="chart-journal-bar" class="chart-container"></div>
    </div>
    <div class="chart-card" id="card-journal-boxplot">
      <div class="card-header">
        <h3>期刊评分箱线图</h3>
        <button class="card-expand-btn" onclick="toggleExpand(this)">⤢</button>
      </div>
      <div id="chart-journal-boxplot" class="chart-container"></div>
    </div>
  </div>
</div>
"""

_DASHBOARD_SCRIPT = """  <script src="assets/vendor/echarts.min.js"></script>
  <script src="assets/vendor/echarts-wordcloud.min.js"></script>
  <script src="assets/vendor/world.js"></script>
  <script src="assets/vendor/sql-wasm.js"></script>
  <script>
  (function () {
    // ============ 国家/地区名映射 ============
    // 不映射 United States，因为 ECharts 世界地图直接用 "United States"
    // world.js 中大部分国家/地区用全名，只有少数需要映射
    var COUNTRY_MAP = {
      "South Korea": "Korea",
      "North Korea": "Dem. Rep. Korea",
      "Czech Republic": "Czech Rep.",
      "Dominican Republic": "Dominican Rep.",
      "Bosnia and Herzegovina": "Bosnia and Herz.",
      "Equatorial Guinea": "Eq. Guinea",
      "Western Sahara": "W. Sahara",
      "Democratic Republic of the Congo": "Dem. Rep. Congo",
      "Republic of the Congo": "Congo",
      "Central African Republic": "Central African Rep.",
      "South Sudan": "S. Sudan",
      "Solomon Islands": "Solomon Is.",
      "Falkland Islands": "Falkland Is."
    };

    var FIELDS = [
      "认知神经科学", "系统与环路神经科学", "分子与细胞神经科学",
      "发育神经科学", "感觉与运动神经科学", "计算与理论神经科学",
      "临床与转化神经科学", "社会与情感神经科学", "方法学"
    ];

    // ============ 数据库加载（主线程）============
    var db = null;

    function query(sql) {
      return new Promise(function (resolve) {
        if (!db) { resolve(null); return; }
        try {
          var results = db.exec(sql);
          resolve(results);
        } catch (err) {
          console.error("SQL error:", err.message);
          resolve(null);
        }
      });
    }

    function onDbReady() {
      document.getElementById("db-loading").hidden = true;
      document.getElementById("dashboard-controls").hidden = false;
      document.getElementById("dashboard-charts").hidden = false;
      initControls();
      updateAllCharts();
    }

    function showDbError(msg) {
      document.getElementById("db-loading").hidden = true;
      document.getElementById("db-error").hidden = false;
      var p = document.querySelector("#db-error p");
      if (p) p.textContent = "数据库加载失败：" + (msg || "未知错误");
    }

    function initDatabase() {
      if (location.protocol === "file:") {
        showDbError("Dashboard 需要通过 HTTP 服务器访问。请在项目目录运行：python -m http.server 8765，然后打开 http://localhost:8765/dashboard.html");
        return;
      }
      if (typeof initSqlJs === "undefined") {
        showDbError("sql.js 未加载");
        return;
      }
      initSqlJs({ locateFile: function(f) { return "assets/vendor/" + f; } })
        .then(function(SQL) {
          var dbName = "slim_db_cache", storeName = "db";
          function fetchDb() {
            fetch("assets/data/literature_slim.db")
              .then(function(r) { return r.arrayBuffer(); })
              .then(function(buf) {
                var data = new Uint8Array(buf);
                db = new SQL.Database(data);
                try {
                  var req = indexedDB.open(dbName, 1);
                  req.onupgradeneeded = function(e) { e.target.result.createObjectStore(storeName); };
                  req.onsuccess = function(e) {
                    var idb = e.target.result;
                    var tx = idb.transaction(storeName, "readwrite");
                    tx.objectStore(storeName).put(data, "db");
                  };
                } catch(ex) {}
                onDbReady();
              })
              .catch(function(err) { showDbError(err.message); });
          }
          try {
            var req = indexedDB.open(dbName, 1);
            req.onupgradeneeded = function(e) { e.target.result.createObjectStore(storeName); };
            req.onsuccess = function(e) {
              var idb = e.target.result;
              var tx = idb.transaction(storeName, "readonly");
              var getReq = tx.objectStore(storeName).get("db");
              getReq.onsuccess = function() {
                if (getReq.result) { db = new SQL.Database(getReq.result); onDbReady(); }
                else { fetchDb(); }
              };
              getReq.onerror = function() { fetchDb(); };
            };
            req.onerror = function() { fetchDb(); };
          } catch(ex) { fetchDb(); }
        })
        .catch(function(err) { showDbError(err.message); });
    }

    initDatabase();

    function parseResult(results, numFields) {
      if (!results || !results.length) return [];
      var r = results[0];
      numFields = numFields || [];
      return r.values.map(function (row) {
        var obj = {};
        r.columns.forEach(function (col, i) {
          obj[col] = row[i];
          if (numFields.indexOf(col) >= 0) obj[col] = Number(row[i]) || 0;
        });
        return obj;
      });
    }

    // ============ 筛选状态 ============
    var dateStart = null, dateEnd = null;
    var selectedFields = new Set(FIELDS);
    var radarMode = "overall";
    var radarNormalize = "absolute";
    var radarCountries = new Set();
    var radarCountryList = [];
    var trendMode = "week";
    var trendSmooth = false;
    var fieldTrendMode = "week";
    var countryTrendMode = "week";
    var wordcloudStyle = "blue";
    var scoreRadarMode = "overall";
    var selectedScoreRadarCountries = [];

    function dateWhere() {
      var conds = [];
      if (dateStart) conds.push("a.pub_date >= '" + dateStart + "'");
      if (dateEnd) conds.push("a.pub_date <= '" + dateEnd + "'");
      return conds.length ? conds.join(" AND ") : "1=1";
    }

    function fieldWhere() {
      if (selectedFields.size === 0) return "1=0";
      var list = Array.from(selectedFields).map(function (f) { return "'" + f + "'"; }).join(",");
      return "t.name IN (" + list + ")";
    }

    // ============ 控件初始化 ============
    function initControls() {
      // 日期范围
      var dateStartEl = document.getElementById("date-start");
      var dateEndEl = document.getElementById("date-end");

      dateStartEl.addEventListener("change", function () {
        dateStart = dateStartEl.value || null;
        updateAllCharts();
      });
      dateEndEl.addEventListener("change", function () {
        dateEnd = dateEndEl.value || null;
        updateAllCharts();
      });

      document.getElementById("btn-all-dates").addEventListener("click", function () {
        dateStart = null; dateEnd = null;
        dateStartEl.value = ""; dateEndEl.value = "";
        updateAllCharts();
      });

      document.getElementById("btn-recent-4w").addEventListener("click", function () {
        var end = new Date();
        var start = new Date(end.getTime() - 28 * 86400000);
        dateStart = start.toISOString().slice(0, 10);
        dateEnd = end.toISOString().slice(0, 10);
        dateStartEl.value = dateStart;
        dateEndEl.value = dateEnd;
        updateAllCharts();
      });

      // 领域复选框
      var fcb = document.getElementById("field-checkboxes");
      FIELDS.forEach(function (field) {
        var label = document.createElement("label");
        label.style.marginRight = "8px";
        var cb = document.createElement("input");
        cb.type = "checkbox";
        cb.checked = true;
        cb.dataset.field = field;
        cb.addEventListener("change", function () {
          if (cb.checked) selectedFields.add(field);
          else selectedFields.delete(field);
          updateAllCharts();
        });
        label.appendChild(cb);
        label.appendChild(document.createTextNode(field.replace("神经科学", "").replace("与", "与")));
        fcb.appendChild(label);
      });

      document.getElementById("btn-all-fields").addEventListener("click", function () {
        selectedFields = new Set(FIELDS);
        fcb.querySelectorAll("input[type=checkbox]").forEach(function (cb) { cb.checked = true; });
        updateAllCharts();
      });
      document.getElementById("btn-no-fields").addEventListener("click", function () {
        selectedFields.clear();
        fcb.querySelectorAll("input[type=checkbox]").forEach(function (cb) { cb.checked = false; });
        updateAllCharts();
      });

      // 归一化模式
      document.getElementById("normalize-mode").addEventListener("change", function () {
        renderCountryFieldHeatmap();
      });

      // 雷达图模式
      document.getElementById("radar-mode").addEventListener("change", function () {
        radarMode = this.value;
        var countrySelect = document.getElementById("radar-country-select");
        if (radarMode === "country") {
          countrySelect.hidden = false;
          if (radarCountryList.length === 0) buildRadarCountrySelect();
          else renderFieldRadar();
        } else {
          countrySelect.hidden = true;
          renderFieldRadar();
        }
      });
      document.getElementById("radar-normalize").addEventListener("change", function () {
        radarNormalize = this.value;
        renderFieldRadar();
      });

      // 评分雷达图模式
      var srm = document.getElementById("score-radar-mode");
      if (srm) {
        srm.addEventListener("change", function () {
          scoreRadarMode = this.value;
          if (scoreRadarMode === "country") {
            buildScoreRadarCountrySelect();
          }
          var sc = document.getElementById("score-radar-country-select");
          if (sc) sc.hidden = scoreRadarMode !== "country";
          renderScoreRadar();
        });
      }

      // 时间趋势模式
      var trendBtns = document.querySelectorAll(".trend-mode");
      trendBtns.forEach(function (btn) {
        btn.addEventListener("click", function () {
          trendBtns.forEach(function(b){ b.classList.remove("active"); });
          btn.classList.add("active");
          trendMode = btn.dataset.mode;
          renderTimeTrend();
        });
      });

      // 时间趋势平滑
      var trendSmoothEl = document.getElementById("trend-smooth");
      if (trendSmoothEl) {
        trendSmoothEl.addEventListener("change", function () {
          trendSmooth = trendSmoothEl.checked;
          renderTimeTrend();
        });
      }

      // 领域时间趋势模式
      var fieldTrendBtns = document.querySelectorAll(".field-trend-mode");
      fieldTrendBtns.forEach(function (btn) {
        btn.addEventListener("click", function () {
          fieldTrendBtns.forEach(function(b){ b.classList.remove("active"); });
          btn.classList.add("active");
          fieldTrendMode = btn.dataset.mode;
          renderFieldTrend();
        });
      });

      // 国家/地区发文趋势模式
      var countryTrendBtns = document.querySelectorAll(".country-trend-mode");
      countryTrendBtns.forEach(function (btn) {
        btn.addEventListener("click", function () {
          countryTrendBtns.forEach(function(b){ b.classList.remove("active"); });
          btn.classList.add("active");
          countryTrendMode = btn.dataset.mode;
          renderCountryTrend();
        });
      });

      // 词云国家/地区筛选
      var wcCountrySelect = document.getElementById("wordcloud-country");
      if (wcCountrySelect) {
        var wcSql = "SELECT c.standard_name as country, COUNT(DISTINCT a.id) as cnt " +
          "FROM articles a JOIN article_countries ac ON a.id=ac.article_id " +
          "JOIN countries c ON ac.country_id=c.id " +
          "GROUP BY c.standard_name ORDER BY cnt DESC LIMIT 30";
        query(wcSql).then(function (res) {
          var data = parseResult(res, ["cnt"]);
          data.forEach(function (d) {
            var opt = document.createElement("option");
            opt.value = d.country;
            opt.textContent = d.country;
            wcCountrySelect.appendChild(opt);
          });
        });
        wcCountrySelect.addEventListener("change", function () {
          renderWordcloud();
        });
      }

      // 词云颜色风格
      var wcs = document.getElementById("wordcloud-style");
      if (wcs) {
        wcs.addEventListener("change", function () {
          wordcloudStyle = this.value;
          renderWordcloud();
        });
      }
    }

    // ============ 图表实例 ============
    var charts = {};

    function getChart(id) {
      if (!charts[id]) {
        var el = document.getElementById(id);
        if (!el) return null;
        charts[id] = echarts.init(el);
      }
      return charts[id];
    }

    // ============ 更新所有图表 ============
    function updateAllCharts() {
      renderCountryHeatmap();
      renderCountryScoreHeatmap();
      renderCountryFieldHeatmap();
      renderScoreDist();
      renderFieldRadar();
      renderScoreRadar();
      renderTimeTrend();
      renderFieldTrend();
      renderCountryTrend();
      renderJournalBar();
      renderJournalBoxplot();
      renderInstitutionScatter();
      renderWordcloud();
    }

    // ============ 1. 国家/地区发文量热力图 ============
    function renderCountryHeatmap() {
      var sql = "SELECT c.standard_name as country, COUNT(DISTINCT a.id) as cnt " +
        "FROM articles a JOIN article_countries ac ON a.id=ac.article_id " +
        "JOIN countries c ON ac.country_id=c.id " +
        "WHERE " + dateWhere() + " " +
        "GROUP BY c.standard_name ORDER BY cnt DESC";
      query(sql).then(function (res) {
        var data = parseResult(res, ["cnt"]);
        var mapData = data.map(function (d) {
          var name = COUNTRY_MAP[d.country] || d.country;
          return { name: name, value: Number(d.cnt) || 0 };
        });
        var chart = getChart("chart-country-heatmap");
        if (chart) chart.setOption({
          tooltip: { trigger: "item", formatter: "{b}: {c}" },
          visualMap: { min: 0, max: Math.max.apply(null, data.map(function(d){return d.cnt;}))||1, left: 10, bottom: 10, text: ["多", "少"], inRange: { color: ["#e0f3f8", "#0868ac"] } },
          series: [{ type: "map", map: "world", roam: true, data: mapData,
            emphasis: { label: { show: true } } }]
        }, true);
      });
    }

    // ============ 2. 国家/地区平均评分热力图 ============
    function renderCountryScoreHeatmap() {
      var sql = "SELECT c.standard_name as country, AVG(a.score) as avg_score " +
        "FROM articles a JOIN article_countries ac ON a.id=ac.article_id " +
        "JOIN countries c ON ac.country_id=c.id " +
        "WHERE a.score > 0 AND " + dateWhere() + " " +
        "GROUP BY c.standard_name ORDER BY avg_score DESC";
      query(sql).then(function (res) {
        var data = parseResult(res, ["avg_score"]);
        var mapData = data.map(function (d) {
          var name = COUNTRY_MAP[d.country] || d.country;
          return { name: name, value: parseFloat(d.avg_score).toFixed(1) };
        });
        var chart = getChart("chart-country-score");
        if (chart) chart.setOption({
          tooltip: { trigger: "item", formatter: "{b}: {c}" },
          visualMap: { min: 3, max: 9, left: 10, bottom: 10, text: ["高", "低"], inRange: { color: ["#fee0d2", "#de2d26"] } },
          series: [{ type: "map", map: "world", roam: true, data: mapData,
            emphasis: { label: { show: true } } }]
        }, true);
      });
    }

    // ============ 3. 国家/地区×领域交叉热力图 ============
    function renderCountryFieldHeatmap() {
      var fieldList = Array.from(selectedFields).map(function(f){return "'"+f+"'";}).join(",");
      if (!fieldList) { var ch = getChart("chart-country-field"); if (ch) ch.clear(); return; }
      var sql = "SELECT c.standard_name as country, t.name as field, COUNT(DISTINCT a.id) as cnt " +
        "FROM articles a " +
        "JOIN article_countries ac ON a.id=ac.article_id JOIN countries c ON ac.country_id=c.id " +
        "JOIN article_themes at ON a.id=at.article_id JOIN themes t ON at.theme_id=t.id " +
        "WHERE " + dateWhere() + " AND t.name IN (" + fieldList + ") " +
        "GROUP BY c.standard_name, t.name";
      query(sql).then(function (res) {
        var data = parseResult(res, ["cnt"]);
        var fields = FIELDS.filter(function(f){return selectedFields.has(f);});
        var mode = document.getElementById("normalize-mode").value;

        // Compute column sums across all data
        var colSums = {};
        fields.forEach(function(f){ colSums[f] = 0; });
        data.forEach(function(d){
          if (colSums[d.field] !== undefined) colSums[d.field] += d.cnt;
        });

        // Compute country sums and sorting metric based on mode
        var countrySums = {};
        var countryMetric = {};
        data.forEach(function(d){
          countrySums[d.country] = (countrySums[d.country]||0) + d.cnt;
          if (mode === "contribution" && colSums[d.field] > 0) {
            countryMetric[d.country] = (countryMetric[d.country]||0) + d.cnt / colSums[d.field];
          }
        });
        if (mode !== "contribution") {
          Object.keys(countrySums).forEach(function(c) {
            countryMetric[c] = countrySums[c];
          });
        }

        // Sort by metric, take top 15
        var topCountries = Object.keys(countrySums).sort(function(a,b){
          return (countryMetric[b]||0) - (countryMetric[a]||0);
        }).slice(0,15).reverse();

        // Compute row sums for top countries
        var rowSums = {};
        topCountries.forEach(function(c){ rowSums[c] = 0; });
        data.forEach(function(d){
          if (rowSums[d.country] !== undefined) rowSums[d.country] += d.cnt;
        });

        var heatData = [];
        topCountries.forEach(function(country, yi) {
          fields.forEach(function(field, xi) {
            var raw = 0;
            var found = data.filter(function(d){return d.country===country && d.field===field;});
            if (found.length) raw = found[0].cnt;
            var val = raw;
            if (mode === "contribution" && colSums[field] > 0) val = raw / colSums[field];
            else if (mode === "focus" && rowSums[country] > 0) val = raw / rowSums[country];
            heatData.push([xi, yi, val]);
          });
        });

        var chart = getChart("chart-country-field");
        if (chart) chart.setOption({
          tooltip: { position: "top",
            formatter: function(p) {
              return topCountries[p.value[1]] + " × " + fields[p.value[0]] + "<br>" +
                (mode === "absolute" ? "数量: " : "比例: ") + (p.value[2]*100).toFixed(1) + (mode === "absolute" ? "" : "%");
            }
          },
          grid: { left: 120, right: 60, top: 20, bottom: 80 },
          xAxis: { type: "category", data: fields, axisLabel: { rotate: 30, fontSize: 10 } },
          yAxis: { type: "category", data: topCountries, axisLabel: { fontSize: 10 } },
          visualMap: { min: 0, max: Math.max.apply(null, heatData.map(function(d){return d[2];}))||1,
            calculable: true, orient: "vertical", right: 0, top: "center",
            inRange: { color: ["#f7fbff", "#08306b"] } },
          series: [{ type: "heatmap", data: heatData,
            label: { show: mode === "absolute", fontSize: 8 },
            emphasis: { itemStyle: { shadowBlur: 10, shadowColor: "rgba(0,0,0,0.5)" } } }]
        }, true);
      });
    }

    // ============ 4. 评分分布 ============
    function renderScoreDist() {
      var sql = "SELECT CAST(a.score AS INTEGER) as bin, COUNT(*) as cnt " +
        "FROM articles a WHERE a.score > 0 AND " + dateWhere() + " " +
        "GROUP BY bin ORDER BY bin";
      query(sql).then(function (res) {
        var data = parseResult(res, ["bin", "cnt"]);
        var bins = [], counts = [];
        for (var i = 0; i <= 10; i++) {
          bins.push(String(i));
          var found = data.filter(function(d){return d.bin === i;});
          counts.push(found.length ? found[0].cnt : 0);
        }
        var chart = getChart("chart-score-dist");
        if (chart) chart.setOption({
          tooltip: { trigger: "axis" },
          xAxis: { type: "category", data: bins, name: "评分区间" },
          yAxis: { type: "value", name: "论文数" },
          series: [{ type: "bar", data: counts, itemStyle: { color: "#0868ac" },
            label: { show: true, position: "top", fontSize: 10 } }]
        }, true);
      });
    }

    // ============ 5. 研究领域分布（雷达图）============
    function shortFieldName(f) {
      return f.replace("神经科学", "").substring(0, 6);
    }

    function buildRadarCountrySelect() {
      var sql = "SELECT c.standard_name as country, COUNT(DISTINCT a.id) as cnt " +
        "FROM articles a JOIN article_countries ac ON a.id=ac.article_id " +
        "JOIN countries c ON ac.country_id=c.id " +
        "GROUP BY c.standard_name ORDER BY cnt DESC LIMIT 15";
      query(sql).then(function (res) {
        var data = parseResult(res, ["cnt"]);
        radarCountryList = ["World"].concat(data.map(function(d){return d.country;}));
        if (radarCountries.size === 0) {
          radarCountries.add("World");
          radarCountryList.slice(1, 3).forEach(function(c){ radarCountries.add(c); });
        }
        var container = document.getElementById("radar-country-select");
        container.innerHTML = "";
        radarCountryList.forEach(function (country) {
          var label = document.createElement("label");
          label.style.marginRight = "8px";
          var cb = document.createElement("input");
          cb.type = "checkbox";
          cb.checked = radarCountries.has(country);
          cb.dataset.country = country;
          cb.addEventListener("change", function () {
            if (cb.checked) {
              if (radarCountries.size >= 5) { cb.checked = false; return; }
              radarCountries.add(country);
            } else {
              radarCountries.delete(country);
            }
            renderFieldRadar();
          });
          label.appendChild(cb);
          label.appendChild(document.createTextNode(country));
          container.appendChild(label);
        });
        renderFieldRadar();
      });
    }

    function renderFieldRadar() {
      var fieldList = Array.from(selectedFields).map(function(f){return "'"+f+"'";}).join(",");
      if (!fieldList) { var ch = getChart("chart-field-radar"); if (ch) ch.clear(); return; }
      var fields = FIELDS.filter(function(f){return selectedFields.has(f);});

      if (radarMode === "overall") {
        var sql = "SELECT t.name as field, COUNT(DISTINCT a.id) as cnt " +
          "FROM articles a JOIN article_themes at ON a.id=at.article_id " +
          "JOIN themes t ON at.theme_id=t.id " +
          "WHERE " + dateWhere() + " AND t.name IN (" + fieldList + ") " +
          "GROUP BY t.name";
        query(sql).then(function (res) {
          var data = parseResult(res, ["cnt"]);
          var maxCnt = Math.max.apply(null, data.map(function(d){return d.cnt;}))||1;
          var indicators = fields.map(function(f){
            return { name: shortFieldName(f), max: maxCnt };
          });
          var values = fields.map(function(f){
            var found = data.filter(function(d){return d.field===f;});
            return found.length ? found[0].cnt : 0;
          });
          var chart = getChart("chart-field-radar");
          if (chart) chart.setOption({
            tooltip: { formatter: function(p) {
              var vals = p.value || [];
              var lines = [p.name];
              fields.forEach(function(f, i) {
                var v = vals[i] || 0;
                lines.push(shortFieldName(f) + ": " + v + " 篇");
              });
              return lines.join("<br>");
            }},
            radar: {
              indicator: indicators,
              radius: "65%",
              splitNumber: 5,
              axisName: { color: "#666", fontSize: 11 },
              splitLine: { lineStyle: { color: "#ddd" } },
              splitArea: { show: true, areaStyle: { color: ["rgba(8,104,172,0.05)", "rgba(8,104,172,0.1)"] } },
              axisLine: { lineStyle: { color: "#ddd" } }
            },
            series: [{ type: "radar", data: [{ value: values, name: "论文数" }],
              itemStyle: { color: "#0868ac" }, areaStyle: { opacity: 0.3 } }]
          }, true);
        });
      } else {
        if (radarCountries.size === 0) { var ch2 = getChart("chart-field-radar"); if (ch2) ch2.clear(); return; }
        var selectedRadarCountries = Array.from(radarCountries);
        // Build per-country queries (World has no country filter)
        var promises = selectedRadarCountries.map(function(country) {
          var sql;
          if (country === "World") {
            sql = "SELECT t.name as field, COUNT(DISTINCT a.id) as cnt " +
              "FROM articles a JOIN article_themes at ON a.id=at.article_id " +
              "JOIN themes t ON at.theme_id=t.id " +
              "JOIN article_countries ac ON a.id=ac.article_id " +
              "WHERE " + dateWhere() + " AND t.name IN (" + fieldList + ") " +
              "GROUP BY t.name";
          } else {
            sql = "SELECT c.standard_name as country, t.name as field, COUNT(DISTINCT a.id) as cnt " +
              "FROM articles a " +
              "JOIN article_countries ac ON a.id=ac.article_id JOIN countries c ON ac.country_id=c.id " +
              "JOIN article_themes at ON a.id=at.article_id JOIN themes t ON at.theme_id=t.id " +
              "WHERE " + dateWhere() + " AND t.name IN (" + fieldList + ") " +
              "AND c.standard_name = '" + country + "' " +
              "GROUP BY c.standard_name, t.name";
          }
          return query(sql).then(function(res) {
            return { country: country, data: parseResult(res, ["cnt"]) };
          });
        });
        // Normalization data for contribution mode
        var promiseNorm = Promise.resolve(null);
        if (radarNormalize === "contribution") {
          var sqlNorm = "SELECT t.name as field, COUNT(DISTINCT a.id) as cnt " +
            "FROM articles a JOIN article_themes at ON a.id=at.article_id " +
            "JOIN themes t ON at.theme_id=t.id " +
            "JOIN article_countries ac ON a.id=ac.article_id " +
            "WHERE " + dateWhere() + " AND t.name IN (" + fieldList + ") " +
            "GROUP BY t.name";
          promiseNorm = query(sqlNorm).then(function(r){return parseResult(r, ["cnt"]);});
        }
        Promise.all(promises).then(function(results) {
          return promiseNorm.then(function(normData) {
            var fieldTotals = {};
            if (normData) normData.forEach(function(d){fieldTotals[d.field]=d.cnt;});
            var maxVal = 0;
            var seriesData = results.map(function(result) {
              var country = result.country;
              var data = result.data;
              var countryTotal = 0;
              data.forEach(function(d){ countryTotal += d.cnt; });
              var values = fields.map(function(f) {
                var found = data.filter(function(d){return d.field === f;});
                var raw = found.length ? found[0].cnt : 0;
                var val = raw;
                if (radarNormalize === "contribution" && fieldTotals[f] > 0) val = raw / fieldTotals[f];
                else if (radarNormalize === "focus" && countryTotal > 0) val = raw / countryTotal;
                if (val > maxVal) maxVal = val;
                return val;
              });
              return { value: values, name: country };
            });
            var indicators = fields.map(function(f){
              return { name: shortFieldName(f), max: maxVal || 1 };
            });
            var colors = ["#0868ac", "#de2d26", "#f4a582", "#92c5de", "#ca0020"];
            var tooltipFormatter = function(p){
              var vals = p.value || [];
              var lines = [p.name];
              fields.forEach(function(f, i){
                var v = vals[i] || 0;
                var label = shortFieldName(f);
                if (radarNormalize === "absolute") lines.push(label + ": " + v + " 篇");
                else lines.push(label + ": " + (v*100).toFixed(1) + "%");
              });
              return lines.join("<br>");
            };
            var chart = getChart("chart-field-radar");
            if (chart) chart.setOption({
              tooltip: { formatter: tooltipFormatter },
              legend: { data: selectedRadarCountries, bottom: 0, textStyle: { fontSize: 10 } },
              radar: {
                indicator: indicators,
                radius: "60%",
                splitNumber: 5,
                axisName: { color: "#666", fontSize: 11 },
                splitLine: { lineStyle: { color: "#ddd" } },
                splitArea: { show: true, areaStyle: { color: ["rgba(8,104,172,0.05)", "rgba(8,104,172,0.1)"] } },
                axisLine: { lineStyle: { color: "#ddd" } }
              },
              series: [{ type: "radar", data: seriesData.map(function(s, i){
                return { value: s.value, name: s.name,
                  itemStyle: { color: colors[i % colors.length] },
                  areaStyle: { opacity: 0.15 } };
              }) }]
            }, true);
          });
        });
      }
    }

    // ============ 5b. 国家/地区评分领域分布（雷达图）============
    function buildScoreRadarCountrySelect() {
      var container = document.getElementById("score-radar-country-select");
      if (!container) return;
      container.innerHTML = "";

      query("SELECT c.standard_name as country, COUNT(DISTINCT a.id) as cnt " +
        "FROM articles a JOIN article_countries ac ON a.id=ac.article_id " +
        "JOIN countries c ON ac.country_id=c.id " +
        "WHERE a.score > 0 AND " + dateWhere() + " " +
        "GROUP BY c.standard_name ORDER BY cnt DESC LIMIT 15")
        .then(function (res) {
          var data = parseResult(res, ["cnt"]);
          var worldLabel = document.createElement("label");
          worldLabel.style.marginRight = "8px";
          var worldCb = document.createElement("input");
          worldCb.type = "checkbox";
          worldCb.checked = true;
          worldCb.dataset.country = "World";
          worldLabel.appendChild(worldCb);
          worldLabel.appendChild(document.createTextNode(" World"));
          container.appendChild(worldLabel);
          worldCb.addEventListener("change", function () {
            updateScoreRadarCountrySelection();
          });

          data.forEach(function (item, idx) {
            var label = document.createElement("label");
            label.style.marginRight = "8px";
            var cb = document.createElement("input");
            cb.type = "checkbox";
            cb.checked = idx < 3;  // 默认选TOP3
            cb.dataset.country = item.country;
            label.appendChild(cb);
            label.appendChild(document.createTextNode(" " + item.country));
            container.appendChild(label);
            cb.addEventListener("change", function () {
              var checked = container.querySelectorAll('input[type="checkbox"]:checked');
              if (checked.length > 5) {
                this.checked = false;
                return;
              }
              updateScoreRadarCountrySelection();
            });
          });
          updateScoreRadarCountrySelection();
        });
    }

    function updateScoreRadarCountrySelection() {
      var container = document.getElementById("score-radar-country-select");
      if (!container) return;
      selectedScoreRadarCountries = [];
      container.querySelectorAll('input[type="checkbox"]:checked').forEach(function (cb) {
        selectedScoreRadarCountries.push(cb.dataset.country);
      });
      renderScoreRadar();
    }

    function renderScoreRadar() {
      if (!db) return;

      var fields = FIELDS.filter(function (f) { return selectedFields.has(f); });
      if (!fields.length) { var ch = getChart("chart-score-radar"); if (ch) ch.clear(); return; }
      var fieldList = fields.map(function (f) { return "'" + f + "'"; }).join(",");
      var indicators = fields.map(function (f) { return { name: shortFieldName(f), max: 10 }; });

      if (scoreRadarMode === "overall") {
        var sql = "SELECT t.name as field, AVG(a.score) as avg_score " +
          "FROM articles a JOIN article_themes at ON a.id=at.article_id " +
          "JOIN themes t ON at.theme_id=t.id " +
          "WHERE a.score > 0 AND " + dateWhere() + " AND t.name IN (" + fieldList + ") " +
          "GROUP BY t.name";

        query(sql).then(function (res) {
          var data = parseResult(res, ["avg_score"]);
          var values = fields.map(function (f) {
            var item = data.find(function (d) { return d.field === f; });
            return item ? Number(item.avg_score).toFixed(2) : 0;
          });

          var chart = getChart("chart-score-radar");
          if (chart) chart.setOption({
            tooltip: {
              formatter: function (params) {
                var html = "整体评分<br/>";
                params.value.forEach(function (v, i) {
                  html += fields[i] + ": " + Number(v).toFixed(2) + "<br/>";
                });
                return html;
              }
            },
            radar: {
              indicator: indicators,
              radius: "65%",
              splitNumber: 5,
              axisName: { color: "#666", fontSize: 11 },
              splitLine: { lineStyle: { color: "#ddd" } },
              splitArea: { show: true, areaStyle: { color: ["rgba(8,104,172,0.05)", "rgba(8,104,172,0.1)"] } },
              axisLine: { lineStyle: { color: "#ddd" } }
            },
            series: [{
              type: "radar",
              data: [{ value: values, name: "整体评分", areaStyle: { color: "rgba(8,104,172,0.2)" }, lineStyle: { color: "#0868ac" } }],
              symbolSize: 5
            }]
          }, true);
        });
      } else {
        if (!selectedScoreRadarCountries.length) {
          var chart = getChart("chart-score-radar");
          if (chart) chart.clear();
          return;
        }

        var colors = ["#0868ac", "#e6550d", "#31a354", "#756bb1", "#e7298a"];
        var seriesData = [];
        var promises = [];

        selectedScoreRadarCountries.forEach(function (country, idx) {
          var sql;
          if (country === "World") {
            sql = "SELECT t.name as field, AVG(a.score) as avg_score " +
              "FROM articles a JOIN article_themes at ON a.id=at.article_id " +
              "JOIN themes t ON at.theme_id=t.id " +
              "JOIN article_countries ac ON a.id=ac.article_id " +
              "WHERE a.score > 0 AND " + dateWhere() + " AND t.name IN (" + fieldList + ") " +
              "GROUP BY t.name";
          } else {
            sql = "SELECT t.name as field, AVG(a.score) as avg_score " +
              "FROM articles a JOIN article_themes at ON a.id=at.article_id " +
              "JOIN themes t ON at.theme_id=t.id " +
              "JOIN article_countries ac ON a.id=ac.article_id " +
              "JOIN countries c ON ac.country_id=c.id " +
              "WHERE a.score > 0 AND c.standard_name='" + country.replace(/'/g, "''") + "' AND " + dateWhere() + " AND t.name IN (" + fieldList + ") " +
              "GROUP BY t.name";
          }

          promises.push(query(sql).then(function (res) {
            var data = parseResult(res, ["avg_score"]);
            var values = fields.map(function (f) {
              var item = data.find(function (d) { return d.field === f; });
              return item ? Number(item.avg_score).toFixed(2) : 0;
            });
            seriesData.push({
              value: values,
              name: country,
              lineStyle: { color: colors[idx % colors.length] },
              areaStyle: { color: colors[idx % colors.length], opacity: 0.1 },
              itemStyle: { color: colors[idx % colors.length] }
            });
          }));
        });

        Promise.all(promises).then(function () {
          var chart = getChart("chart-score-radar");
          if (chart) chart.setOption({
            tooltip: {
              formatter: function (params) {
                var html = params.name + "<br/>";
                params.value.forEach(function (v, i) {
                  html += fields[i] + ": " + Number(v).toFixed(2) + "<br/>";
                });
                return html;
              }
            },
            legend: { bottom: 0, type: "scroll" },
            radar: {
              indicator: indicators,
              radius: "65%",
              splitNumber: 5,
              axisName: { color: "#666", fontSize: 11 },
              splitLine: { lineStyle: { color: "#ddd" } },
              splitArea: { show: true, areaStyle: { color: ["rgba(8,104,172,0.05)", "rgba(8,104,172,0.1)"] } },
              axisLine: { lineStyle: { color: "#ddd" } }
            },
            series: [{
              type: "radar",
              data: seriesData,
              symbolSize: 5
            }]
          }, true);
        });
      }
    }

    // ============ 6. 时间趋势 ============
    function smooth(arr) {
      if (arr.length < 3) return arr;
      var result = [];
      for (var i = 0; i < arr.length; i++) {
        if (i === 0) result.push((arr[0] + arr[1]) / 2);
        else if (i === arr.length - 1) result.push((arr[i-1] + arr[i]) / 2);
        else result.push((arr[i-1] + arr[i] + arr[i+1]) / 3);
      }
      return result;
    }

    function renderTimeTrend() {
      var sql = "SELECT a.pub_date as dt, COUNT(*) as cnt, AVG(a.score) as avg_score " +
        "FROM articles a WHERE a.pub_date IS NOT NULL AND " + dateWhere() + " " +
        "GROUP BY a.pub_date ORDER BY a.pub_date";
      query(sql).then(function (res) {
        var data = parseResult(res, ["cnt", "avg_score"]);
        var buckets = {};
        data.forEach(function(d){
          var key;
          if (trendMode === "week") {
            var dt = new Date(d.dt);
            var weekStart = new Date(dt);
            weekStart.setDate(dt.getDate() - dt.getDay());
            key = weekStart.toISOString().slice(0,10);
          } else {
            key = d.dt;
          }
          if (!buckets[key]) buckets[key] = { cnt: 0, scoreSum: 0, scoreCnt: 0 };
          buckets[key].cnt += d.cnt;
          if (d.avg_score > 0) { buckets[key].scoreSum += d.avg_score * d.cnt; buckets[key].scoreCnt += d.cnt; }
        });
        var dates = Object.keys(buckets).sort();
        var counts = dates.map(function(k){return buckets[k].cnt;});
        var scores = dates.map(function(k){return buckets[k].scoreCnt > 0 ? parseFloat((buckets[k].scoreSum / buckets[k].scoreCnt).toFixed(2)) : 0;});

        var chart = getChart("chart-time-trend");
        if (chart) chart.setOption({
          tooltip: { trigger: "axis" },
          legend: { data: ["发文量", "平均评分"] },
          xAxis: { type: "category", data: dates, axisLabel: { rotate: 30, fontSize: 10 } },
          yAxis: [
            { type: "value", name: "发文量", position: "left" },
            { type: "value", name: "评分", position: "right", min: 0, max: 10 }
          ],
          series: [
            { name: "发文量", type: "line", data: counts, itemStyle: { color: "#0868ac" }, smooth: true },
            { name: "平均评分", type: "line", yAxisIndex: 1, data: scores, itemStyle: { color: "#de2d26" }, smooth: true }
          ]
        }, true);
      });
    }

    // ============ 6b. 领域时间趋势（堆叠面积图）============
    function renderFieldTrend() {
      if (!db) return;
      var fields = FIELDS.filter(function(f) { return !selectedFields.size || selectedFields.has(f); });
      var fieldList = fields.map(function(f) { return "'" + f + "'"; }).join(",");

      // 按周或按天聚合
      var dateExpr;
      if (fieldTrendMode === "week") {
        dateExpr = "strftime('%Y-%m-%d', pub_date, 'weekday 0', '-6 days')";  // 周一
      } else {
        dateExpr = "pub_date";
      }

      var sql = "SELECT " + dateExpr + " as dt, t.name as field, COUNT(DISTINCT a.id) as cnt " +
        "FROM articles a JOIN article_themes at ON a.id=at.article_id " +
        "JOIN themes t ON at.theme_id=t.id " +
        "WHERE " + dateWhere() + " AND t.name IN (" + fieldList + ") " +
        "GROUP BY dt, t.name ORDER BY dt";

      query(sql).then(function(res) {
        var data = parseResult(res, ["cnt"]);
        // 收集所有日期
        var datesSet = {};
        data.forEach(function(d) { datesSet[d.dt] = true; });
        var dates = Object.keys(datesSet).sort();

        // 为每个领域构建数据系列
        var series = fields.map(function(field) {
          var values = dates.map(function(dt) {
            var item = data.find(function(d) { return d.dt === dt && d.field === field; });
            return item ? Number(item.cnt) : 0;
          });
          return {
            name: field,
            type: "line",
            stack: "总量",
            areaStyle: { opacity: 0.3 },
            emphasis: { focus: "series" },
            data: values
          };
        });

        var chart = getChart("chart-field-trend");
        if (chart) chart.setOption({
          tooltip: { trigger: "axis", axisPointer: { type: "cross" } },
          legend: { bottom: 0, type: "scroll" },
          grid: { left: 50, right: 20, top: 20, bottom: 60 },
          xAxis: { type: "category", data: dates, axisLabel: { rotate: 30 } },
          yAxis: { type: "value", name: "论文数" },
          series: series
        }, true);
      });
    }

    // ============ 6c. 国家/地区发文趋势（堆叠面积图）============
    function renderCountryTrend() {
      if (!db) return;

      // 先查询发文量TOP10国家/地区
      var topSql = "SELECT c.standard_name as country, COUNT(DISTINCT a.id) as cnt " +
        "FROM articles a JOIN article_countries ac ON a.id=ac.article_id " +
        "JOIN countries c ON ac.country_id=c.id " +
        "WHERE " + dateWhere() +
        " GROUP BY c.standard_name ORDER BY cnt DESC LIMIT 10";

      query(topSql).then(function(topRes) {
        var topCountries = parseResult(topRes, ["cnt"]).map(function(d) { return d.country; });
        var countryList = topCountries.map(function(c) { return "'" + c.replace(/'/g, "''") + "'"; }).join(",");

        var dateExpr;
        if (countryTrendMode === "week") {
          dateExpr = "strftime('%Y-%m-%d', pub_date, 'weekday 0', '-6 days')";
        } else {
          dateExpr = "pub_date";
        }

        var sql = "SELECT " + dateExpr + " as dt, c.standard_name as country, COUNT(DISTINCT a.id) as cnt " +
          "FROM articles a JOIN article_countries ac ON a.id=ac.article_id " +
          "JOIN countries c ON ac.country_id=c.id " +
          "WHERE " + dateWhere() + " AND c.standard_name IN (" + countryList + ") " +
          "GROUP BY dt, c.standard_name ORDER BY dt";

        return query(sql);
      }).then(function(res) {
        var data = parseResult(res, ["cnt"]);
        var datesSet = {};
        data.forEach(function(d) { datesSet[d.dt] = true; });
        var dates = Object.keys(datesSet).sort();

        // 重新查询TOP10国家/地区列表（因为上一个promise的闭包中可能访问不到）
        var topCountries = data.length > 0 ?
          Array.from(new Set(data.map(function(d) { return d.country; }))) : [];

        var series = topCountries.map(function(country) {
          var values = dates.map(function(dt) {
            var item = data.find(function(d) { return d.dt === dt && d.country === country; });
            return item ? Number(item.cnt) : 0;
          });
          return {
            name: country,
            type: "line",
            stack: "总量",
            areaStyle: { opacity: 0.3 },
            emphasis: { focus: "series" },
            data: values
          };
        });

        var chart = getChart("chart-country-trend");
        if (chart) chart.setOption({
          tooltip: { trigger: "axis", axisPointer: { type: "cross" } },
          legend: { bottom: 0, type: "scroll" },
          grid: { left: 50, right: 20, top: 20, bottom: 60 },
          xAxis: { type: "category", data: dates, axisLabel: { rotate: 30 } },
          yAxis: { type: "value", name: "论文数" },
          series: series
        }, true);
      });
    }

    // ============ 7. 期刊发文量TOP20 ============
    function renderJournalBar() {
      var sql = "SELECT a.journal as journal, COUNT(*) as cnt, AVG(a.score) as avg_score " +
        "FROM articles a WHERE a.journal IS NOT NULL AND " + dateWhere() + " " +
        "GROUP BY a.journal ORDER BY cnt DESC LIMIT 20";
      query(sql).then(function (res) {
        var data = parseResult(res, ["cnt", "avg_score"]);
        data.reverse();
        var chart = getChart("chart-journal-bar");
        if (chart) chart.setOption({
          tooltip: { trigger: "axis", formatter: function(p){ return p[0].name + ": " + p[0].value + " 篇"; } },
          grid: { left: 120, right: 20, top: 10, bottom: 20 },
          xAxis: { type: "value" },
          yAxis: { type: "category", data: data.map(function(d){return d.journal;}), axisLabel: { fontSize: 10 } },
          series: [{ type: "bar", data: data.map(function(d){return d.cnt;}),
            itemStyle: { color: "#0868ac" }, label: { show: true, position: "right", fontSize: 10 } }]
        }, true);
      });
    }

    // ============ 7b. 期刊评分箱线图 ============
    function renderJournalBoxplot() {
      if (!db) return;

      // 查询TOP15期刊的所有评分
      var sql = "SELECT a.journal as journal, a.score as score " +
        "FROM articles a " +
        "WHERE a.score > 0 AND a.journal IS NOT NULL AND " + dateWhere() +
        " AND a.journal IN (" +
        "  SELECT journal FROM articles WHERE score > 0 AND journal IS NOT NULL AND " + dateWhere() +
        "  GROUP BY journal ORDER BY COUNT(*) DESC LIMIT 15" +
        ")";

      query(sql).then(function(res) {
        var data = parseResult(res, ["score"]);

        // 按期刊分组
        var groups = {};
        data.forEach(function(d) {
          if (!groups[d.journal]) groups[d.journal] = [];
          groups[d.journal].push(Number(d.score));
        });

        // 计算每组的统计量
        var journals = Object.keys(groups);
        // 按发文量排序
        journals.sort(function(a, b) { return groups[b].length - groups[a].length; });

        var boxData = journals.map(function(j) {
          var scores = groups[j].sort(function(a, b) { return a - b; });
          var n = scores.length;
          var q1 = scores[Math.floor(n * 0.25)];
          var median = scores[Math.floor(n * 0.5)];
          var q3 = scores[Math.floor(n * 0.75)];
          var min = scores[0];
          var max = scores[n - 1];
          return [min, q1, median, q3, max];
        });

        var chart = getChart("chart-journal-boxplot");
        if (chart) chart.setOption({
          tooltip: { trigger: "item" },
          grid: { left: 150, right: 20, top: 20, bottom: 20 },
          xAxis: { type: "value", name: "评分", min: 0, max: 10 },
          yAxis: { type: "category", data: journals, inverse: true },
          series: [{
            name: "评分分布",
            type: "boxplot",
            data: boxData,
            itemStyle: { color: "rgba(8,104,172,0.3)", borderColor: "#0868ac" }
          }]
        }, true);
      });
    }

    // ============ 8. 机构排名散点图 ============
    function renderInstitutionScatter() {
      var sql = "SELECT i.name as inst, COUNT(DISTINCT a.id) as cnt, AVG(a.score) as avg_score, " +
        "AVG(a.score * a.score) - AVG(a.score) * AVG(a.score) as var_score " +
        "FROM articles a JOIN article_institutions ai ON a.id=ai.article_id " +
        "JOIN institutions i ON ai.institution_id=i.id " +
        "WHERE a.score > 0 AND " + dateWhere() + " " +
        "GROUP BY i.name ORDER BY cnt DESC LIMIT 30";
      query(sql).then(function (res) {
        var data = parseResult(res, ["cnt", "avg_score", "var_score"]);
        var scatterData = data.map(function(d){
          return [d.cnt, parseFloat(d.avg_score).toFixed(2), d.inst, d.var_score];
        });
        var chart = getChart("chart-institution-scatter");
        if (chart) chart.setOption({
          tooltip: { formatter: function(p){ return p.value[2] + "<br>发文量: " + p.value[0] + "<br>评分: " + p.value[1]; } },
          xAxis: { type: "value", name: "发文量", nameLocation: "middle", nameGap: 25 },
          yAxis: { type: "value", name: "平均评分", min: 0, max: 10 },
          series: [{ type: "scatter", data: scatterData,
            symbolSize: function(v) {
              var variance = v[3] || 0;
              return Math.max(8, Math.sqrt(variance) * 10);
            },
            label: {
              show: true,
              formatter: function(p) { return p.value[2]; },
              fontSize: 9,
              position: "right",
              color: "#333"
            },
            labelLayout: { hideOverlap: true },
            itemStyle: { color: "#0868ac", opacity: 0.7 } }]
        }, true);
      });
    }

    // ============ 9. 交叉标签词云 ============
    function getWordColor(style) {
      if (style === "blue") {
        return function () {
          return "rgb(" +
            Math.round(Math.random() * 50 + 30) + "," +
            Math.round(Math.random() * 100 + 50) + "," +
            Math.round(Math.random() * 100 + 100) + ")";
        };
      }
      if (style === "rainbow") {
        return function () {
          var hue = Math.random() * 360;
          return "hsl(" + hue + ",70%,50%)";
        };
      }
      if (style === "warm") {
        return function () {
          var hue = Math.random() * 60;
          return "hsl(" + hue + ",75%,55%)";
        };
      }
      if (style === "cool") {
        return function () {
          var hue = 150 + Math.random() * 120;
          return "hsl(" + hue + ",65%,50%)";
        };
      }
      if (style === "red") {
        return function () {
          var hue = Math.random() * 30 - 10;  // -10到20: 偏红
          return "hsl(" + (hue + 360) % 360 + ",75%,50%)";
        };
      }
      if (style === "green") {
        return function () {
          var hue = 80 + Math.random() * 60;  // 80-140: 绿色范围
          return "hsl(" + hue + ",65%,45%)";
        };
      }
      if (style === "purple") {
        return function () {
          var hue = 250 + Math.random() * 40;  // 250-290: 紫色范围
          return "hsl(" + hue + ",65%,50%)";
        };
      }
      return function () { return "#0868ac"; };
    }

    function renderWordcloud() {
      var wcCountryEl = document.getElementById("wordcloud-country");
      var country = wcCountryEl ? wcCountryEl.value : "";
      var sql;
      if (country) {
        sql = "SELECT ct.name as tag, COUNT(*) as cnt " +
          "FROM article_crosstags act JOIN crosstags ct ON act.tag_id=ct.id " +
          "JOIN articles a ON act.article_id=a.id " +
          "JOIN article_countries ac ON a.id=ac.article_id " +
          "JOIN countries c ON ac.country_id=c.id " +
          "WHERE c.standard_name = '" + country + "' AND " + dateWhere() + " " +
          "GROUP BY ct.name ORDER BY cnt DESC LIMIT 50";
      } else {
        sql = "SELECT ct.name as tag, COUNT(*) as cnt " +
          "FROM article_crosstags act JOIN crosstags ct ON act.tag_id=ct.id " +
          "JOIN articles a ON act.article_id=a.id " +
          "WHERE " + dateWhere() + " " +
          "GROUP BY ct.name ORDER BY cnt DESC LIMIT 50";
      }
      query(sql).then(function (res) {
        var data = parseResult(res, ["cnt"]);
        var cloudData = data.map(function(d){return {name: d.tag, value: d.cnt};});
        var chart = getChart("chart-wordcloud");
        if (chart) chart.setOption({
          tooltip: { formatter: "{b}: {c}" },
          series: [{ type: "wordCloud", shape: "square", left: "center", top: "center", width: "100%", height: "100%",
            sizeRange: [12, 50], rotationRange: [0, 0], rotationStep: 0, gridSize: 8, drawOutOfBound: false,
            textStyle: { fontFamily: "sans-serif", fontWeight: "bold",
              color: getWordColor(wordcloudStyle) },
            emphasis: { focus: "self", textStyle: { shadowBlur: 10, shadowColor: "#333" } },
            data: cloudData }]
        }, true);
      });
    }

    // ============ 卡片展开/收起 ============
    window.toggleExpand = function(btn) {
      var card = btn.closest('.chart-card');
      card.classList.toggle('expanded');
      // 通知ECharts重新resize
      setTimeout(function() {
        var chartId = card.querySelector('.chart-container').id;
        var chart = echarts.getInstanceByDom(document.getElementById(chartId));
        if (chart) chart.resize();
      }, 100);
      // 更新按钮图标
      btn.textContent = card.classList.contains('expanded') ? '⤡' : '⤢';
    };

    // 窗口大小变化时重绘
    window.addEventListener("resize", function() {
      Object.keys(charts).forEach(function(id) {
        if (charts[id]) charts[id].resize();
      });
    });
  })();
  </script>
"""

# ============ Dashboard 专属样式 ============
_DASHBOARD_STYLE = """<style>
#db-loading { text-align: center; padding: 40px 0; }
.loading-spinner { width: 32px; height: 32px; border: 3px solid #e0e0e0; border-top-color: #0868ac; border-radius: 50%; margin: 12px auto; animation: spin 0.8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
#dashboard-controls { background: #f8f9fa; border-radius: 8px; padding: 16px; margin-bottom: 20px; }
.control-row { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin-bottom: 10px; }
.control-row:last-child { margin-bottom: 0; }
.control-row label { font-weight: 600; white-space: nowrap; }
.date-input { padding: 4px 8px; border: 1px solid #ccc; border-radius: 4px; font-size: 13px; }
.ctrl-btn { padding: 4px 10px; border: 1px solid #ccc; border-radius: 4px; background: #fff; cursor: pointer; font-size: 12px; }
.ctrl-btn:hover { background: #f0f0f0; }
#field-checkboxes label { font-weight: normal; font-size: 13px; }
#radar-country-select label { font-weight: normal; font-size: 13px; margin-right: 8px; }
#score-radar-country-select label { font-weight: normal; font-size: 13px; margin-right: 8px; }
.chart-controls { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin-bottom: 8px; }
.trend-mode.active, .field-trend-mode.active, .country-trend-mode.active { background: #0868ac; color: #fff; border-color: #0868ac; }
.chart-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 16px; margin-top: 16px; }
.chart-card { background: #fff; border: 1px solid #e0e0e0; border-radius: 8px; padding: 12px; }
.card-header { display: flex; justify-content: space-between; align-items: center; }
.card-expand-btn { background: none; border: 1px solid #ddd; border-radius: 4px; padding: 2px 8px; cursor: pointer; font-size: 14px; color: #666; }
.card-expand-btn:hover { background: #f0f0f0; }
.chart-card h3 { margin: 0 0 8px; font-size: 14px; color: #333; }
.chart-wide { grid-column: span 2; }
.chart-container { width: 100%; height: 400px; }
.chart-card.expanded { grid-column: 1 / -1; }
.chart-card.expanded .chart-container { height: 500px; }
@media (max-width: 900px) { .chart-grid { grid-template-columns: 1fr; } .chart-wide { grid-column: span 1; } .chart-container { height: 300px; } }
</style>"""
