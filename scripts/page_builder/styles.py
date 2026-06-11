from __future__ import annotations


CSS = """
:root {
  color-scheme: light;
  --bg: #f7f8fb;
  --paper: #ffffff;
  --ink: #17202a;
  --muted: #5e6b78;
  --line: #dfe4ea;
  --accent: #1769aa;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans", "Helvetica Neue", Arial, sans-serif;
  line-height: 1.65;
  color: var(--ink);
  background: var(--bg);
}
html {
  scroll-behavior: smooth;
}
header {
  border-bottom: 1px solid var(--line);
  background: var(--paper);
}
.wrap {
  width: min(1080px, calc(100% - 32px));
  margin: 0 auto;
}
.site-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 18px 0;
}
.brand {
  font-size: 18px;
  font-weight: 700;
  color: var(--ink);
  text-decoration: none;
}
.nav a {
  color: var(--muted);
  text-decoration: none;
  margin-left: 16px;
}
main {
  padding: 28px 0 48px;
}
.cover-hero {
  width: min(60%, 980px);
  margin: 0 auto;
  overflow: hidden;
}
.cover-hero img {
  display: block;
  width: 100%;
  height: auto;
}
.cover-hero + main {
  margin-top: -96px;
  position: relative;
}
.paper {
  background: var(--paper);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 28px;
}
.article-card {
  margin: 22px 0;
  padding: 20px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: #fbfdff;
}
.article-card h3 {
  margin-top: 0;
  color: var(--accent);
}
.article-card h3 a {
  color: inherit;
  text-decoration: none;
}
.article-card h3 a:hover {
  text-decoration: underline;
}
.article-card-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}
.article-card-head h3 {
  margin-bottom: 10px;
}
.article-card-actions {
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  gap: 8px;
}
.article-badge {
  padding: 5px 10px;
  border-radius: 999px;
  background: #e9f3ff;
  color: #0f5d9e;
  font-size: 13px;
  font-weight: 700;
  white-space: nowrap;
}
.favorite-toggle,
.favorite-tray-button,
.favorite-close,
.favorite-actions button,
.favorite-item button {
  font: inherit;
}
.favorite-toggle {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 30px;
  padding: 5px 9px;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: #ffffff;
  color: var(--muted);
  cursor: pointer;
}
.favorite-toggle img,
.favorite-tray-button img {
  width: 16px;
  height: 16px;
}
.favorite-toggle.active {
  border-color: #b7d7ef;
  background: #e9f3ff;
  color: var(--accent);
  font-weight: 700;
}
.favorite-tray-button {
  position: fixed;
  right: 18px;
  bottom: 18px;
  z-index: 35;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-width: 58px;
  height: 42px;
  padding: 8px 12px;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: var(--paper);
  color: var(--accent);
  box-shadow: 0 12px 32px rgba(23, 32, 42, 0.14);
  cursor: pointer;
}
.favorite-tray-button span {
  min-width: 18px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}
.favorite-drawer {
  position: fixed;
  right: 18px;
  bottom: 72px;
  z-index: 34;
  width: min(380px, calc(100vw - 32px));
  max-height: min(640px, calc(100vh - 104px));
  display: flex;
  flex-direction: column;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.97);
  box-shadow: 0 18px 48px rgba(23, 32, 42, 0.18);
  backdrop-filter: blur(10px);
}
.favorite-drawer[hidden] {
  display: none;
}
.favorite-drawer-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 16px 10px;
  border-bottom: 1px solid var(--line);
}
.favorite-drawer-head span {
  display: block;
  color: var(--muted);
  font-size: 13px;
}
.favorite-close {
  width: 30px;
  height: 30px;
  border: 1px solid var(--line);
  border-radius: 50%;
  background: #ffffff;
  color: var(--muted);
  cursor: pointer;
}
.favorite-list {
  display: grid;
  gap: 8px;
  overflow: auto;
  padding: 12px 16px;
}
.favorite-empty {
  margin: 0;
  color: var(--muted);
}
.favorite-item {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 10px;
  align-items: center;
  padding: 10px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: #fbfdff;
}
.favorite-item a {
  color: var(--accent);
  font-weight: 700;
  line-height: 1.35;
  text-decoration: none;
}
.favorite-item button,
.favorite-actions button {
  border: 1px solid var(--line);
  border-radius: 999px;
  background: #ffffff;
  color: var(--muted);
  cursor: pointer;
}
.favorite-item button {
  padding: 5px 9px;
  white-space: nowrap;
}
.favorite-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 12px 16px 14px;
  border-top: 1px solid var(--line);
}
.favorite-actions button {
  padding: 7px 11px;
}
.article-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 4px 0 16px;
}
.article-chip {
  display: inline-flex;
  align-items: center;
  max-width: 100%;
  padding: 4px 9px;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: #ffffff;
  color: var(--muted);
  font-size: 13px;
  line-height: 1.3;
}
.article-card p:last-child,
.article-card ul:last-child {
  margin-bottom: 0;
}
.report-list {
  display: grid;
  gap: 12px;
  padding: 0;
  list-style: none;
}
.report-list a {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 132px;
  align-items: center;
  gap: 16px;
  padding: 14px 16px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--paper);
  color: var(--accent);
  text-decoration: none;
}
.report-thumb {
  width: 132px;
  aspect-ratio: 16 / 10;
  object-fit: cover;
  border-radius: 6px;
}
h1, h2, h3 {
  line-height: 1.25;
}
h1 { font-size: 30px; }
h2 {
  margin-top: 34px;
  padding-bottom: 6px;
  border-bottom: 1px solid var(--line);
}
table {
  width: 100%;
  border-collapse: collapse;
  margin: 16px 0 22px;
  font-size: 15px;
}
th, td {
  border: 1px solid var(--line);
  padding: 8px 10px;
  vertical-align: top;
}
th { background: #eef3f8; }
code, pre {
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
}
pre {
  overflow-x: auto;
  padding: 14px;
  border-radius: 8px;
  background: #101828;
  color: #f8fafc;
}
blockquote {
  margin-left: 0;
  padding-left: 16px;
  border-left: 4px solid var(--line);
  color: var(--muted);
}
img {
  max-width: 100%;
  height: auto;
}
.meta {
  color: var(--muted);
}
.report-media {
  display: grid;
  gap: 20px;
  margin: 28px 0;
}
.chart-grid {
  display: grid;
  gap: 18px;
}
.chart-frame {
  width: 100%;
  aspect-ratio: 16 / 9;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: transparent;
}
.stats-figure {
  margin: 0;
}
.stats-figure img {
  display: block;
  width: 100%;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: #fff;
}
.floating-toc {
  position: fixed;
  top: 92px;
  right: 16px;
  z-index: 20;
  width: 180px;
  max-height: calc(100vh - 116px);
  overflow: auto;
  padding: 12px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.94);
  box-shadow: 0 12px 32px rgba(23, 32, 42, 0.10);
  backdrop-filter: blur(10px);
}
.floating-toc-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  color: var(--ink);
  font-size: 13px;
  font-weight: 700;
}
.reading-progress-percent {
  color: var(--accent);
  font-variant-numeric: tabular-nums;
}
.reading-progress {
  height: 4px;
  margin: 9px 0 10px;
  border-radius: 999px;
  background: #e8edf3;
  overflow: hidden;
}
.reading-progress-value {
  display: block;
  width: 0%;
  height: 100%;
  border-radius: inherit;
  background: var(--accent);
}
.floating-toc nav {
  display: grid;
  gap: 4px;
}
.floating-toc a {
  display: block;
  padding: 5px 7px;
  border-radius: 6px;
  color: var(--muted);
  font-size: 13px;
  line-height: 1.35;
  text-decoration: none;
}
.floating-toc a:hover,
.floating-toc a.active {
  color: var(--accent);
  background: #e9f3ff;
}
.floating-toc a.toc-level-3 {
  margin-left: 10px;
  padding-left: 10px;
  border-left: 2px solid #d7e5f2;
  font-size: 12px;
}
@media (max-width: 1280px) {
  .floating-toc {
    display: none;
  }
}
@media (max-width: 680px) {
  .site-head { align-items: flex-start; flex-direction: column; }
  .nav a { margin-left: 0; margin-right: 14px; }
  .cover-hero { width: 100%; }
  .cover-hero + main { margin-top: -36px; }
  .paper { padding: 18px; }
  .article-card-head { flex-direction: column; gap: 6px; }
  .article-card-actions { flex-wrap: wrap; }
  .report-list a { grid-template-columns: 1fr; }
  .report-thumb { width: 100%; }
  .favorite-tray-button { right: 12px; bottom: 12px; }
  .favorite-drawer { right: 12px; bottom: 62px; }
  table { display: block; overflow-x: auto; white-space: nowrap; }
}
@media print {
  .floating-toc,
  .favorite-toggle,
  .favorite-tray-button,
  .favorite-drawer {
    display: none;
  }
}
.video-embed {
  position: relative;
  width: 100%;
  aspect-ratio: 16 / 9;
  margin: 24px 0;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid var(--line);
  background: #000;
}

.video-embed iframe {
  width: 100%;
  height: 100%;
  display: block;
}
"""
