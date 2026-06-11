from __future__ import annotations


def favorites_panel(root_prefix: str = "") -> str:
    folder_src = f"{root_prefix}assets/icons/folder.svg"
    return f"""
  <button class="favorite-tray-button" type="button" data-favorite-open aria-label="打开收藏夹">
    <img src="{folder_src}" alt="">
    <span data-favorite-count>0</span>
  </button>
  <aside class="favorite-drawer" data-favorite-drawer hidden aria-label="收藏夹">
    <div class="favorite-drawer-head">
      <div>
        <strong>收藏夹</strong>
        <span data-favorite-summary>暂无收藏</span>
      </div>
      <button class="favorite-close" type="button" data-favorite-close aria-label="关闭收藏夹">×</button>
    </div>
    <div class="favorite-list" data-favorite-list></div>
    <div class="favorite-actions">
      <button type="button" data-favorite-copy>复制 Markdown</button>
      <button type="button" data-favorite-download>下载 .md</button>
      <button type="button" data-favorite-clear>清空</button>
    </div>
  </aside>
"""


def favorites_script() -> str:
    return """  <script>
    (function () {
      var STORAGE_KEY = "scientific-bulletin:favorites";
      var drawer = document.querySelector("[data-favorite-drawer]");
      var list = document.querySelector("[data-favorite-list]");
      var countNodes = Array.prototype.slice.call(document.querySelectorAll("[data-favorite-count]"));
      var summary = document.querySelector("[data-favorite-summary]");
      if (!drawer || !list) return;

      function loadFavorites() {
        try {
          return JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
        } catch (error) {
          return [];
        }
      }

      function saveFavorites(items) {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(items));
      }

      function favoriteFromCard(card) {
        return {
          id: card.dataset.favoriteId,
          title: card.dataset.favoriteTitle || "Untitled",
          url: card.dataset.favoriteUrl || location.href,
          pageTitle: document.title.replace(/\\s+\\|\\s+Neuroscience Bulletin$/, ""),
          pageUrl: location.href.split("#")[0],
          markdown: card.dataset.favoriteMarkdown || card.innerText.trim()
        };
      }

      function toMarkdown(items) {
        if (!items.length) return "# 神经科学快讯收藏\\n\\n暂无收藏。\\n";
        var lines = ["# 神经科学快讯收藏", ""];
        items.forEach(function (item, index) {
          lines.push("## " + (index + 1) + ". " + item.title);
          lines.push("");
          if (item.url) lines.push("- 链接: " + item.url);
          if (item.pageTitle) lines.push("- 来源报告: [" + item.pageTitle + "](" + item.pageUrl + ")");
          lines.push("");
          lines.push(item.markdown || item.title);
          lines.push("");
          lines.push("---");
          lines.push("");
        });
        return lines.join("\\n");
      }

      function downloadText(filename, text) {
        var blob = new Blob([text], { type: "text/markdown;charset=utf-8" });
        var url = URL.createObjectURL(blob);
        var link = document.createElement("a");
        link.href = url;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(url);
      }

      function updateButtons(items) {
        var ids = new Set(items.map(function (item) { return item.id; }));
        document.querySelectorAll("[data-favorite-toggle]").forEach(function (button) {
          var card = button.closest(".article-card");
          var active = card && ids.has(card.dataset.favoriteId);
          button.classList.toggle("active", Boolean(active));
          button.setAttribute("aria-pressed", active ? "true" : "false");
          button.querySelector("span").textContent = active ? "已收藏" : "收藏";
        });
      }

      function renderFavorites() {
        var items = loadFavorites();
        countNodes.forEach(function (node) { node.textContent = String(items.length); });
        if (summary) summary.textContent = items.length ? items.length + " 篇文章" : "暂无收藏";
        if (!items.length) {
          list.innerHTML = '<p class="favorite-empty">还没有收藏文章。</p>';
        } else {
          list.innerHTML = items.map(function (item) {
            return '<article class="favorite-item">'
              + '<a href="' + escapeHtml(item.url || item.pageUrl || "#") + '">' + escapeHtml(item.title) + '</a>'
              + '<button type="button" data-favorite-remove="' + escapeHtml(item.id) + '">移除</button>'
              + '</article>';
          }).join("");
        }
        updateButtons(items);
      }

      function escapeHtml(value) {
        return String(value).replace(/[&<>"']/g, function (char) {
          return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char];
        });
      }

      document.addEventListener("click", function (event) {
        var open = event.target.closest("[data-favorite-open]");
        if (open) {
          drawer.hidden = false;
          renderFavorites();
          return;
        }

        if (event.target.closest("[data-favorite-close]")) {
          drawer.hidden = true;
          return;
        }

        var toggle = event.target.closest("[data-favorite-toggle]");
        if (toggle) {
          var card = toggle.closest(".article-card");
          if (!card) return;
          var items = loadFavorites();
          var existingIndex = items.findIndex(function (item) { return item.id === card.dataset.favoriteId; });
          if (existingIndex >= 0) {
            items.splice(existingIndex, 1);
          } else {
            items.push(favoriteFromCard(card));
          }
          saveFavorites(items);
          renderFavorites();
          return;
        }

        var remove = event.target.closest("[data-favorite-remove]");
        if (remove) {
          saveFavorites(loadFavorites().filter(function (item) { return item.id !== remove.dataset.favoriteRemove; }));
          renderFavorites();
          return;
        }

        if (event.target.closest("[data-favorite-copy]")) {
          navigator.clipboard.writeText(toMarkdown(loadFavorites()));
          return;
        }

        if (event.target.closest("[data-favorite-download]")) {
          downloadText("favorites.md", toMarkdown(loadFavorites()));
          return;
        }

        if (event.target.closest("[data-favorite-clear]")) {
          saveFavorites([]);
          renderFavorites();
        }
      });

      renderFavorites();
    })();
  </script>
"""
