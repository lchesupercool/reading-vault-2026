#!/usr/bin/env python3

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import html
import json
import os
import re
import shutil
from urllib.parse import quote, urlparse


PUBLISH_ROOT = Path(__file__).resolve().parent
DEFAULT_VAULT_ROOT = PUBLISH_ROOT.parent
CONFIG_PATH = PUBLISH_ROOT / "publish.json"
DIST_ROOT = PUBLISH_ROOT / "dist"


def load_publish_config() -> dict[str, object]:
    if not CONFIG_PATH.exists():
        return {}
    try:
        raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid publish config at {CONFIG_PATH}: {exc}") from exc
    if not isinstance(raw, dict):
        raise SystemExit(f"Publish config must be a JSON object: {CONFIG_PATH}")
    return raw


PUBLISH_CONFIG = load_publish_config()
VAULT_ROOT = Path(
    os.environ.get("PUBLISH_VAULT_ROOT")
    or PUBLISH_CONFIG.get("vault_root")
    or DEFAULT_VAULT_ROOT
).expanduser().resolve()
SITE_NAME = str(PUBLISH_CONFIG.get("site_name") or VAULT_ROOT.name)
SITE_TAGLINE = str(
    PUBLISH_CONFIG.get("site_tagline")
    or "沿用 Publish 的目录结构，换成更接近 Claude 的安静阅读界面。"
)
SITE_DESCRIPTION = str(
    PUBLISH_CONFIG.get("site_description")
    or "一个面向公开阅读的 Obsidian 发布站，左侧看目录，中间读正文，右侧看页内结构与关联。"
)

EXCLUDED_ROOT_NAMES = {
    ".git",
    ".obsidian",
    "site",
    "publish",
}

ASSET_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".webp",
    ".pdf",
    ".mp4",
    ".mov",
    ".mp3",
    ".wav",
}

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"}
VIDEO_EXTENSIONS = {".mp4", ".mov"}
AUDIO_EXTENSIONS = {".mp3", ".wav"}

PROPERTY_ORDER = [
    "title",
    "source",
    "author",
    "published",
    "created",
    "description",
    "tags",
]

PROPERTY_LABELS = {
    "title": "title",
    "source": "source",
    "author": "author",
    "published": "published",
    "created": "created",
    "description": "description",
    "tags": "tags",
}

LIST_ITEM_RE = re.compile(r"^(?P<indent>\s*)(?P<marker>(?:[-*+])|(?:\d+\.))\s+(?P<content>.*)$")
HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$")
HR_RE = re.compile(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$")
TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?(?:\s*:?-{3,}:?\s*\|)+\s*:?-{3,}:?\s*\|?\s*$")
INLINE_CODE_RE = re.compile(r"(`+)(.+?)\1")
WIKI_LINK_RE = re.compile(r"(!)?\[\[([^\]|#]+)(?:#([^\]|]+))?(?:\|([^\]]+))?\]\]")
MD_LINK_RE = re.compile(r"(!)?\[([^\]]*)\]\(([^)]+)\)")
BOLD_RE = re.compile(r"(\*\*|__)(.+?)\1")
ITALIC_RE = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)")
BASH_TOKEN_RE = re.compile(r"\s+|[^\s]+")
YAML_KEY_RE = re.compile(r"^(\s*)([A-Za-z0-9_.-]+)(\s*=\s*)(.*)$")
YAML_COLON_RE = re.compile(r"^(\s*)([A-Za-z0-9_.-]+)(\s*:\s*)(.*)$")

SHELL_SUBCOMMAND_HOSTS = {"brew", "git", "ghostty", "npm", "pnpm", "yarn", "uv", "npx"}


def highlight_bash_line(line: str) -> str:
    stripped = line.lstrip()
    if stripped.startswith("#"):
        return f'<span class="tok-comment">{html.escape(line)}</span>'

    parts = BASH_TOKEN_RE.findall(line)
    rendered: list[str] = []
    tokens: list[tuple[int, str]] = []
    for token in parts:
        if token.isspace():
            rendered.append(html.escape(token))
            continue
        token_index = len(tokens)
        tokens.append((len(rendered), token))
        rendered.append(html.escape(token))

    if not tokens:
        return "".join(rendered)

    first_token = tokens[0][1]
    if first_token in SHELL_SUBCOMMAND_HOSTS and len(tokens) > 1:
        second_slot, second_token = tokens[1]
        rendered[second_slot] = f'<span class="tok-accent">{html.escape(second_token)}</span>'

    for slot, token in tokens:
        if token.startswith("+"):
            rendered[slot] = f'<span class="tok-flag">{html.escape(token)}</span>'

    return "".join(rendered)


def highlight_yaml_line(line: str) -> str:
    stripped = line.lstrip()
    if stripped.startswith("#"):
        return f'<span class="tok-comment">{html.escape(line)}</span>'

    for pattern in (YAML_KEY_RE, YAML_COLON_RE):
        match = pattern.match(line)
        if match:
            indent, key, operator, value = match.groups()
            rendered_value = html.escape(value)
            if value.startswith(('"', "'")) and value.endswith(('"', "'")) and len(value) >= 2:
                rendered_value = f'<span class="tok-string">{html.escape(value)}</span>'
            return "".join(
                [
                    html.escape(indent),
                    f'<span class="tok-key">{html.escape(key)}</span>',
                    html.escape(operator),
                    rendered_value,
                ]
            )
    return html.escape(line)


def highlight_code_html(code: str, language_name: str) -> str:
    lines = code.split("\n")
    normalized = language_name.lower()

    if normalized in {"bash", "sh", "shell", "zsh"}:
        return "\n".join(highlight_bash_line(line) for line in lines)
    if normalized in {"yaml", "yml"}:
        return "\n".join(highlight_yaml_line(line) for line in lines)
    return html.escape(code)

STYLE_CSS = """@import url('https://weekly.tw93.fun/fonts/jinkai.css');

:root {
  --page-width: 800px;
  --page-side-padding: 48px;
  --sidebar-left-width: 280px;
  --sidebar-right-width: 300px;
  --font-text: "TsangerJinKai02", "STKaiti", "KaiTi", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif, "Apple Color Emoji", "Segoe UI Emoji";
  --font-quote: "TsangerJinKai02", "STKaiti", "KaiTi", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif, "Apple Color Emoji", "Segoe UI Emoji";
  --font-mono: "SFMono-Regular", Menlo, Monaco, Consolas, "Liberation Mono", monospace;
  --background-primary: #ffffff;
  --background-secondary: #f7f7f7;
  --background-modifier-border: #e0e0e0;
  --background-modifier-border-hover: #b8b8b8;
  --background-modifier-box-shadow: rgba(15, 23, 42, 0.16);
  --text-normal: #222222;
  --text-muted: #666666;
  --text-faint: #999999;
  --text-accent: #8a6cff;
  --code-inline-background: #eef1f2;
  --code-inline-border: rgba(15, 23, 42, 0.08);
  --code-block-background: #f3f6f9;
  --code-block-toolbar-background: #d6dee5;
  --code-block-border: rgba(15, 23, 42, 0.035);
  --code-block-shadow: none;
  --code-block-text: #3b4252;
  --code-block-muted: #1f2937;
  --code-copy-hover: rgba(15, 23, 42, 0.06);
  --code-copy-active: #dcfce7;
  --code-copy-active-text: #166534;
  --code-token-accent: #2563eb;
  --code-token-comment: #94a3b8;
  --code-token-flag: #7c3aed;
  --code-token-string: #0f766e;
  --line-height-normal: 1.65;
  --line-height-tight: 1.35;
  --component-title-size: 14px;
}

body.theme-dark {
  --background-primary: #1e1e1e;
  --background-secondary: #252525;
  --background-modifier-border: #3b3b3b;
  --background-modifier-border-hover: #636363;
  --background-modifier-box-shadow: rgba(0, 0, 0, 0.3);
  --text-normal: #dadada;
  --text-muted: #b1b1b1;
  --text-faint: #8c8c8c;
  --text-accent: #a58cff;
  --code-inline-background: #343941;
  --code-inline-border: rgba(255, 255, 255, 0.08);
  --code-block-background: #1f2430;
  --code-block-toolbar-background: #313948;
  --code-block-border: rgba(255, 255, 255, 0.06);
  --code-block-shadow: none;
  --code-block-text: #d8e1ef;
  --code-block-muted: #eef2f7;
  --code-copy-hover: rgba(255, 255, 255, 0.08);
  --code-copy-active: rgba(34, 197, 94, 0.18);
  --code-copy-active-text: #bbf7d0;
  --code-token-accent: #60a5fa;
  --code-token-comment: #94a3b8;
  --code-token-flag: #c4b5fd;
  --code-token-string: #5eead4;
}

*,
*::before,
*::after {
  box-sizing: border-box;
}

html,
body {
  margin: 0;
  height: 100%;
}

html {
  font-size: 16px;
  scroll-behavior: smooth;
  -webkit-text-size-adjust: 100%;
  text-rendering: optimizeLegibility;
  -webkit-font-smoothing: subpixel-antialiased;
}

body {
  background: var(--background-primary);
  color: var(--text-normal);
  font-family: var(--font-text);
  font-weight: 550;
  line-height: var(--line-height-normal);
  letter-spacing: 0.03em;
  -webkit-font-smoothing: subpixel-antialiased;
  font-synthesis: weight style;
}

button,
input,
textarea,
select {
  font: inherit;
}

a {
  color: var(--text-accent);
  text-decoration: underline;
  text-decoration-thickness: 1px;
  text-underline-offset: 0.14em;
}

img,
video {
  max-width: 100%;
}

code,
pre,
kbd,
samp {
  font-family: var(--font-mono);
  font-weight: 400;
}

.mobile-bar {
  display: none;
}

.published-container {
  width: 100%;
  height: 100%;
  overflow: hidden;
  position: relative;
  display: flex;
  flex-direction: column;
}

.site-body {
  position: relative;
  display: flex;
  width: 100%;
  height: 100%;
  overflow: hidden;
}

.site-body-left-column {
  width: var(--sidebar-left-width);
  flex: 0 0 var(--sidebar-left-width);
  min-width: var(--sidebar-left-width);
  padding: 32px 0 0 18px;
  display: flex;
  flex-direction: column;
  background: var(--background-primary);
  border-right: 1px solid var(--background-modifier-border);
  height: 100%;
}

.site-body-left-column-inner {
  width: var(--sidebar-left-width);
  max-width: 100%;
  margin-left: auto;
  height: 100%;
  display: flex;
  flex-direction: column;
}

.site-body-left-column-site-name {
  color: var(--text-normal);
  font-size: 22px;
  font-weight: 600;
  z-index: 1;
  cursor: pointer;
  line-height: 1.2;
  padding: 4px 32px 32px 0;
  text-decoration: none;
}

.site-body-left-column-site-name:hover {
  color: var(--text-muted);
  text-decoration: none;
}

.site-body-left-column-site-theme-toggle {
  padding: 0 0 14px 0;
  display: flex;
  align-items: center;
  min-height: 40px;
}

.site-body-left-column-site-theme-toggle .checkbox-container {
  cursor: pointer;
  background-color: #efefef;
  border-radius: 14px;
  display: inline-block;
  height: 22px;
  position: relative;
  user-select: none;
  width: 50px;
  border: 0;
  padding: 0;
  overflow: hidden;
  box-shadow: inset 0 0 0 1px rgba(0, 0, 0, 0.08);
}

.site-body-left-column-site-theme-toggle .checkbox-container:hover {
  box-shadow: inset 0 0 0 1px rgba(0, 0, 0, 0.14);
}

.site-body-left-column-site-theme-toggle .checkbox-container::after {
  content: "";
  position: absolute;
  background-color: #fff;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  left: 3px;
  top: 3px;
  transform: translate3d(0, 0, 0);
  transition: transform 0.15s ease-in-out;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.18), inset 0 0 0 1px rgba(0, 0, 0, 0.08);
  z-index: 2;
}

.site-body-left-column-site-theme-toggle .checkbox-container.is-enabled {
  background-color: #3b3b3b;
}

.site-body-left-column-site-theme-toggle .checkbox-container.is-enabled::after {
  transform: translate3d(28px, 0, 0);
}

.site-body-left-column-site-theme-toggle .option {
  display: flex;
  align-items: center;
  justify-content: center;
  position: absolute;
  top: 6px;
  pointer-events: none;
  color: var(--text-faint);
  z-index: 1;
}

.site-body-left-column-site-theme-toggle .option svg {
  width: 10px;
  height: 10px;
  stroke: currentColor;
  stroke-width: 1.8;
  fill: none;
}

.site-body-left-column-site-theme-toggle .option.mod-dark {
  left: 7px;
}

.site-body-left-column-site-theme-toggle .option.mod-light {
  right: 7px;
}

.site-body-left-column-site-theme-toggle.is-dark .option.mod-dark {
  color: #d7d7d7;
}

.site-body-left-column-site-theme-toggle:not(.is-dark) .option.mod-light {
  color: #666666;
}

.nav-search-wrap {
  position: relative;
  width: calc(100% - 18px);
}

.nav-search {
  width: 100%;
  height: 32px;
  border-radius: 6px;
  border: 1px solid var(--background-modifier-border);
  background: var(--background-primary);
  color: var(--text-normal);
  padding: 0 12px 0 34px;
  font: inherit;
  font-size: 14px;
  outline: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='14' height='14' viewBox='0 0 24 24' fill='none' stroke='%23999999' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Ccircle cx='11' cy='11' r='7'/%3E%3Cpath d='m20 20-3.5-3.5'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: 10px center;
}

.nav-search::placeholder {
  color: var(--text-faint);
}

.nav-search:focus {
  border-color: var(--background-modifier-border-hover);
}

.search-results {
  display: none;
  position: absolute;
  top: calc(100% + 6px);
  left: 0;
  right: 0;
  background: var(--background-primary);
  max-height: 420px;
  overflow: auto;
  box-shadow: 0 2px 8px var(--background-modifier-box-shadow);
  border-radius: 8px;
  border: 1px solid var(--background-modifier-border);
  z-index: 50;
  padding: 6px;
}

.search-results.is-visible {
  display: block;
}

.search-result {
  display: block;
  padding: 8px 10px;
  border-radius: 4px;
  color: inherit;
  text-decoration: none;
}

.search-result:hover {
  background: var(--background-secondary);
}

.search-result-title {
  display: block;
  font-size: 14px;
  color: var(--text-normal);
}

.search-result-meta {
  display: block;
  margin-top: 4px;
  color: var(--text-muted);
  font-size: 12px;
}

.nav-tree {
  flex: 1 1 auto;
  overflow: auto;
  padding-bottom: 32px;
  padding-top: 10px;
  scrollbar-gutter: stable;
}

.nav-tree::-webkit-scrollbar,
.site-body-right-column-inner::-webkit-scrollbar {
  width: 8px;
}

.tree-section,
.tree-folder,
.tree-folder-header,
.tree-children {
  margin: 0;
}

.tree-home-link,
.tree-note-link,
.tree-folder-link {
  display: block;
  font-size: 14px;
  line-height: 1.35;
  color: var(--text-muted);
  text-decoration: none;
}

.tree-home-link {
  padding: 5px 18px 10px 16px;
  color: var(--text-accent);
}

.tree-folder-header {
  display: flex;
  align-items: flex-start;
  margin-left: -8px;
  padding: 5px 18px 5px 0;
  color: var(--text-normal);
  font-weight: 500;
}

.tree-toggle {
  display: flex;
  align-items: center;
  width: 18px;
  height: 18px;
  padding: 0;
  margin: 2px 8px 0 0;
  border: 0;
  background: none;
  color: var(--text-faint);
  cursor: pointer;
}

.tree-folder-header.is-collapsed .tree-toggle {
  transform: rotate(-90deg);
}

.tree-folder-link {
  color: var(--text-normal);
}

.tree-folder-link.is-active {
  color: var(--text-accent);
}

.tree-children {
  padding-left: 24px;
  padding-bottom: 8px;
}

.tree-children .tree-children {
  padding-left: 18px;
  border-left: 1px solid var(--background-modifier-border);
}

.tree-children.is-hidden {
  display: none;
}

.tree-note-link {
  margin-left: -1px;
  padding: 5px 0 5px 16px;
  border-left: 1px solid var(--background-modifier-border);
}

.tree-note-link:hover {
  color: var(--text-normal);
  border-left-color: var(--background-modifier-border-hover);
}

.tree-note-link.is-active {
  color: var(--text-accent);
  border-left-color: var(--text-accent);
  font-weight: 500;
}

.site-body-center-column {
  flex: 1 0 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.site-main {
  width: 100%;
  height: 100%;
}

.site-content {
  font-size: 16px;
  line-height: var(--line-height-normal);
  padding: 24px 0 96px;
  margin: 0 auto;
  width: 100%;
  height: 100%;
  position: relative;
  overflow-y: auto;
  overflow-wrap: break-word;
  color: var(--text-normal);
}

.markdown-preview-sizer {
  max-width: var(--page-width);
  margin-right: auto;
  margin-left: auto;
  padding: 0 var(--page-side-padding);
}

.page-header {
  margin-top: 0.25em;
  margin-bottom: 1em;
  font-size: 2.6em;
  line-height: 1.2;
  letter-spacing: 0.01em;
  color: var(--text-normal);
  font-weight: 850;
}

.breadcrumbs,
.article-meta {
  color: var(--text-muted);
  font-size: 13px;
}

.breadcrumbs {
  margin-top: 0.25em;
  margin-bottom: 1.4em;
}

.breadcrumbs a {
  color: var(--text-muted);
  text-decoration: none;
}

.breadcrumbs a:hover {
  color: var(--text-accent);
}

.breadcrumbs span {
  opacity: 0.6;
  padding: 0 6px;
}

.article-summary {
  margin: 0 0 1em;
}

.intro-tagline {
  margin: 0 0 2.2em;
  font-family: var(--font-text);
  font-size: 1.02rem;
  line-height: 1.8;
  color: var(--text-normal);
}

.intro-tagline p {
  margin: 0;
}

.article-meta {
  margin: 0 0 1.75em;
  display: grid;
  gap: 0.22rem;
  line-height: 1.55;
}

.article-meta-line {
  display: block;
}

.note-properties {
  margin: 0 0 2.1em;
}

.note-properties-title {
  margin: 0 0 1.1em;
  font-size: 1.55em;
  font-weight: 760;
  border: 0;
  padding: 0;
}

.note-properties-grid {
  display: grid;
  gap: 16px;
}

.note-property-row {
  display: grid;
  grid-template-columns: 24px 180px minmax(0, 1fr);
  align-items: start;
  column-gap: 16px;
}

.note-property-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  color: var(--text-muted);
}

.note-property-icon svg {
  width: 21px;
  height: 21px;
  stroke: currentColor;
  stroke-width: 1.9;
  fill: none;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.note-property-name {
  padding-top: 1px;
  color: var(--text-muted);
  font-size: 0.98rem;
}

.note-property-value {
  min-width: 0;
  font-size: 0.98rem;
  line-height: 1.65;
}

.note-property-link {
  word-break: break-all;
}

.note-property-list {
  display: grid;
  gap: 6px;
}

.note-property-empty {
  color: var(--text-faint);
}

.note-property-tag {
  display: inline-flex;
  align-items: center;
  margin: 0 10px 8px 0;
  padding: 0.18rem 0.78rem;
  border-radius: 999px;
  background: rgba(138, 108, 255, 0.12);
  color: var(--text-accent);
  font-size: 0.95rem;
  text-decoration: none;
}

.doc-body h1,
.doc-body h2,
h2 {
  border-bottom: 1px solid var(--background-modifier-border);
  padding-bottom: 0.5em;
}

.doc-body h1,
.doc-body h2,
h2 {
  margin: 1.5em 0 0.5em;
  font-size: 1.6em;
  font-weight: 700;
}

.doc-body h3 {
  margin: 1.25em 0 0.25em;
  font-size: 1.35em;
  font-weight: 700;
}

.doc-body h4 {
  margin: 1.25em 0 0.25em;
  font-size: 1.15em;
  font-weight: 700;
}

.doc-body h5,
.doc-body h6 {
  margin: 1em 0 0.25em;
  font-size: 1em;
}

.doc-body p,
.doc-body ul,
.doc-body ol,
.doc-body blockquote,
.doc-body table,
.doc-body pre,
.doc-body hr {
  margin: 0 0 1em;
}

.doc-body ul,
.doc-body ol {
  padding-left: 1.5em;
}

.doc-body blockquote {
  border-left: 2px solid var(--text-accent);
  padding-left: 1em;
  margin-left: 0;
}

.doc-body table {
  width: 100%;
  border-collapse: collapse;
}

.doc-body th,
.doc-body td {
  padding: 8px 10px;
  border: 1px solid var(--background-modifier-border);
  text-align: left;
  vertical-align: top;
}

.doc-body pre {
  position: relative;
  overflow-x: auto;
  padding: 40px 0 0;
  border-radius: 7px;
  border: 1px solid var(--code-block-border);
  background: var(--code-block-background);
  box-shadow: var(--code-block-shadow);
  color: var(--code-block-text);
}

.doc-body pre .code-block-toolbar {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 30px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 8px 0 11px;
  border-top-left-radius: inherit;
  border-top-right-radius: inherit;
  background: var(--code-block-toolbar-background);
}

.doc-body pre .code-block-language {
  color: var(--code-block-muted);
  font-family: var(--font-mono);
  font-size: 0.7rem;
  font-weight: 400;
  line-height: 1;
}

.doc-body pre .code-copy-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  padding: 0;
  border: 0;
  border-radius: 4px;
  background: transparent;
  color: var(--code-block-muted);
  cursor: pointer;
  transition: background-color 140ms ease, color 140ms ease;
}

.doc-body pre .code-copy-button:hover {
  background: var(--code-copy-hover);
  color: var(--text-normal);
}

.doc-body pre .code-copy-button:focus-visible {
  outline: 2px solid var(--text-accent);
  outline-offset: 2px;
}

.doc-body pre .code-copy-button.is-copied {
  background: var(--code-copy-active);
  color: var(--code-copy-active-text);
}

.doc-body pre .code-copy-button svg {
  width: 12px;
  height: 12px;
  stroke: currentColor;
  stroke-width: 1.7;
  fill: none;
}

.doc-body code {
  background: var(--code-inline-background);
  border: 1px solid var(--code-inline-border);
  border-radius: 6px;
  padding: 0.14em 0.38em;
  font-size: 0.92em;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.4);
}

.doc-body pre code {
  display: block;
  min-width: max-content;
  padding: 11px 14px 13px;
  border: 0;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
  color: var(--code-block-text);
  white-space: pre;
  line-height: 1.66;
  font-size: 0.84rem;
  font-weight: 400;
  tab-size: 2;
}

.doc-body pre code .tok-comment {
  color: var(--code-token-comment);
}

.doc-body pre code .tok-accent,
.doc-body pre code .tok-key {
  color: var(--code-token-accent);
}

.doc-body pre code .tok-flag {
  color: var(--code-token-flag);
}

.doc-body pre code .tok-string {
  color: var(--code-token-string);
}

.doc-body strong,
.doc-body b {
  font-weight: 700;
}

.doc-body .asset-link {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.doc-body .asset-embed {
  display: block;
}

.doc-body img,
.doc-body video {
  display: block;
  width: 100%;
  height: auto;
  margin: 0;
  border-radius: 10px;
  border: 1px solid var(--background-modifier-border);
}

.doc-body audio {
  display: block;
  width: 100%;
}

.doc-body .asset-caption {
  display: block;
  margin-top: 0.55rem;
  color: var(--text-muted);
  font-size: 0.9rem;
  text-align: center;
}

.entry-list {
  list-style: none;
  margin: 0 0 2em;
  padding: 0;
}

.entry-list li {
  padding: 0.5em 0 0.8em;
  border-bottom: 1px solid var(--background-modifier-border);
}

.entry-list li:last-child {
  border-bottom: none;
}

.entry-list a {
  font-weight: 500;
}

.entry-meta {
  font-size: 13px;
  color: var(--text-muted);
  margin-top: 0.25em;
}

.entry-summary {
  font-size: 14px;
  color: var(--text-normal);
  margin-top: 0.3em;
}

.site-footer {
  padding: 4px;
  font-size: 12px;
  text-align: right;
  position: fixed;
  bottom: 16px;
  right: 18px;
  z-index: 20;
}

.site-footer a {
  text-decoration: none;
  color: var(--text-faint);
}

.site-footer a:hover {
  color: var(--text-accent);
}

.scrim {
  display: none;
}

@media screen and (max-width: 750px) {
  .mobile-bar {
    display: flex;
    align-items: center;
    gap: 12px;
    height: 50px;
    padding: 12px 18px;
    border-bottom: 1px solid var(--background-modifier-border);
    background: var(--background-primary);
  }

  .mobile-menu {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 28px;
    height: 28px;
    border: 0;
    background: transparent;
    color: var(--text-muted);
    font-size: 20px;
    cursor: pointer;
  }

  .mobile-title {
    font-size: 18px;
    font-weight: 600;
    color: var(--text-normal);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .published-container {
    height: calc(100% - 50px);
  }

  .site-body-left-column {
    position: fixed;
    top: 50px;
    left: 0;
    bottom: 0;
    z-index: 40;
    transform: translateX(-100%);
    transition: transform 180ms ease;
    box-shadow: 0 8px 32px var(--background-modifier-box-shadow);
  }

  body.nav-open .site-body-left-column {
    transform: translateX(0);
  }

  .scrim {
    position: fixed;
    inset: 50px 0 0;
    background: rgba(0, 0, 0, 0.35);
    opacity: 0;
    pointer-events: none;
    transition: opacity 180ms ease;
    z-index: 30;
  }

  body.nav-open .scrim {
    display: block;
    opacity: 1;
    pointer-events: auto;
  }

  .markdown-preview-sizer {
    padding: 0 24px;
  }

  .page-header {
    font-size: 2em;
  }

  .note-property-row {
    grid-template-columns: 24px minmax(0, 1fr);
    row-gap: 6px;
  }

  .note-property-value {
    grid-column: 2 / -1;
  }

  .site-footer {
    display: none;
  }
}
"""

APP_JS = """(() => {
  const body = document.body;
  const scrim = document.querySelector('.scrim');
  const menu = document.querySelector('.mobile-menu');
  const themeToggle = document.querySelector('.theme-toggle');
  const themeToggleWrap = document.querySelector('.site-body-left-column-site-theme-toggle');
  const searchInput = document.querySelector('.nav-search');
  const searchResults = document.querySelector('.search-results');
  const tocLinks = Array.from(document.querySelectorAll('.toc-link'));
  const rootPrefix = body.dataset.rootPrefix || '';
  const headings = tocLinks
    .map((link) => document.getElementById(link.getAttribute('href').slice(1)))
    .filter(Boolean);
  const searchIndex = Array.isArray(window.__PUBLISH_SEARCH_INDEX) ? window.__PUBLISH_SEARCH_INDEX : [];

  const closeNav = () => body.classList.remove('nav-open');
  const setTheme = (themeName) => {
    body.classList.remove('theme-light', 'theme-dark');
    body.classList.add(themeName);
    const isDark = themeName === 'theme-dark';
    if (themeToggle) themeToggle.classList.toggle('is-enabled', isDark);
    if (themeToggleWrap) themeToggleWrap.classList.toggle('is-dark', isDark);
    try {
      localStorage.setItem('site-theme', isDark ? 'dark' : 'light');
    } catch (error) {
      void error;
    }
  };

  let storedTheme = '';
  try {
    storedTheme = localStorage.getItem('site-theme') || '';
  } catch (error) {
    void error;
  }
  setTheme(storedTheme === 'dark' ? 'theme-dark' : 'theme-light');

  if (menu) {
    menu.addEventListener('click', () => {
      body.classList.toggle('nav-open');
    });
  }

  if (themeToggle) {
    themeToggle.addEventListener('click', () => {
      setTheme(body.classList.contains('theme-dark') ? 'theme-light' : 'theme-dark');
    });
  }

  if (scrim) {
    scrim.addEventListener('click', closeNav);
  }

  document.querySelectorAll('.tree-toggle').forEach((button) => {
    button.addEventListener('click', (event) => {
      event.preventDefault();
      const header = button.closest('.tree-folder-header');
      const children = header && header.parentElement ? header.parentElement.querySelector(':scope > .tree-children') : null;
      if (!header || !children) return;
      const collapsed = header.classList.toggle('is-collapsed');
      children.classList.toggle('is-hidden', collapsed);
      button.setAttribute('aria-expanded', String(!collapsed));
    });
  });

  const copyText = async (text) => {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch (error) {
      try {
        const textarea = document.createElement('textarea');
        textarea.value = text;
        textarea.setAttribute('readonly', '');
        textarea.style.position = 'fixed';
        textarea.style.opacity = '0';
        document.body.appendChild(textarea);
        textarea.select();
        const copied = document.execCommand('copy');
        textarea.remove();
        return copied;
      } catch (fallbackError) {
        void fallbackError;
        return false;
      }
    }
  };

  document.querySelectorAll('.code-copy-button').forEach((button) => {
    let resetTimer = 0;
    button.addEventListener('click', async () => {
      const code = button.closest('pre')?.querySelector('code');
      if (!code) return;
      const copied = await copyText(code.textContent || '');
      if (!copied) return;
      button.classList.add('is-copied');
      button.setAttribute('aria-label', 'Copied');
      button.setAttribute('title', 'Copied');
      window.clearTimeout(resetTimer);
      resetTimer = window.setTimeout(() => {
        button.classList.remove('is-copied');
        button.setAttribute('aria-label', 'Copy code');
        button.setAttribute('title', 'Copy');
      }, 1400);
    });
  });

  const scoreResult = (query, item) => {
    const haystacks = [
      item.title || '',
      item.path || '',
      item.excerpt || '',
    ].map((value) => value.toLowerCase());
    if (haystacks[0].includes(query)) return 3;
    if (haystacks[1].includes(query)) return 2;
    if (haystacks[2].includes(query)) return 1;
    return 0;
  };

  const renderSearch = (query) => {
    if (!searchInput || !searchResults) return;
    const normalized = query.trim().toLowerCase();
    if (!normalized) {
      searchResults.innerHTML = '';
      searchResults.classList.remove('is-visible');
      return;
    }

    const results = searchIndex
      .map((item) => ({ item, score: scoreResult(normalized, item) }))
      .filter((entry) => entry.score > 0)
      .sort((left, right) => right.score - left.score || left.item.title.localeCompare(right.item.title, 'zh-CN'))
      .slice(0, 10);

    if (!results.length) {
      searchResults.innerHTML = '<div class="search-result"><span class="search-result-title">没有匹配结果</span><span class="search-result-meta">试试标题、路径或正文关键词</span></div>';
      searchResults.classList.add('is-visible');
      return;
    }

    searchResults.innerHTML = results
      .map(({ item }) => [
        '<a class="search-result" href="' + rootPrefix + item.url + '">',
        '<span class="search-result-title">' + item.title + '</span>',
        '<span class="search-result-meta">' + item.path + ' · ' + item.excerpt + '</span>',
        '</a>',
      ].join(''))
      .join('');
    searchResults.classList.add('is-visible');
  };

  if (searchInput) {
    searchInput.addEventListener('input', (event) => {
      renderSearch(event.target.value);
    });
    searchInput.addEventListener('focus', (event) => {
      renderSearch(event.target.value);
    });
    document.addEventListener('click', (event) => {
      if (!searchResults || !searchInput) return;
      if (searchResults.contains(event.target) || searchInput.contains(event.target)) return;
      searchResults.classList.remove('is-visible');
    });
  }

  if (tocLinks.length && headings.length) {
    const observer = new IntersectionObserver((entries) => {
      const visible = entries
        .filter((entry) => entry.isIntersecting)
        .sort((left, right) => left.boundingClientRect.top - right.boundingClientRect.top)[0];
      if (!visible) return;
      const activeId = '#' + visible.target.id;
      tocLinks.forEach((link) => {
        link.classList.toggle('is-active', link.getAttribute('href') === activeId);
      });
    }, {
      rootMargin: '-20% 0px -70% 0px',
      threshold: [0, 1],
    });
    headings.forEach((heading) => observer.observe(heading));
  }
})();
"""


@dataclass
class Heading:
    level: int
    text: str
    anchor: str


@dataclass
class Note:
    source_path: Path
    rel_path: Path
    note_key: str
    output_rel_path: Path
    output_path: Path
    title: str
    frontmatter: dict[str, object]
    body_markdown: str
    plain_text: str
    headings: list[Heading] = field(default_factory=list)
    html_body: str = ""
    links_to: set[str] = field(default_factory=set)
    backlinks: list["Note"] = field(default_factory=list)
    mtime: float = 0.0
    date_label: str = ""
    properties_html: str = ""


@dataclass
class FolderNode:
    name: str
    rel_path: Path
    children: dict[str, "FolderNode"] = field(default_factory=dict)
    notes: list[Note] = field(default_factory=list)

    @property
    def note_count(self) -> int:
        total = len(self.notes)
        for child in self.children.values():
            total += child.note_count
        return total


def should_skip(path: Path) -> bool:
    try:
        rel = path.relative_to(VAULT_ROOT)
    except ValueError:
        return True
    parts = rel.parts
    return bool(parts) and parts[0] in EXCLUDED_ROOT_NAMES


def iter_markdown_files() -> list[Path]:
    return sorted(
        path
        for path in VAULT_ROOT.rglob("*.md")
        if path.is_file() and not should_skip(path)
    )


def iter_assets() -> list[Path]:
    return sorted(
        path
        for path in VAULT_ROOT.rglob("*")
        if path.is_file()
        and path.suffix.lower() in ASSET_EXTENSIONS
        and not should_skip(path)
    )


def strip_frontmatter(text: str) -> tuple[dict[str, object], str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text

    for index in range(1, min(len(lines), 80)):
        if lines[index].strip() == "---":
            frontmatter: dict[str, object] = {}
            current_key = ""
            for raw_line in lines[1:index]:
                if not raw_line.strip():
                    continue
                stripped = raw_line.strip()
                if stripped.startswith("#"):
                    continue
                if raw_line[:1].isspace() and stripped.startswith("- ") and current_key:
                    entry = parse_scalar(stripped[2:].strip())
                    existing = frontmatter.get(current_key, "")
                    if isinstance(existing, list):
                        existing.append(entry)
                    elif existing in {"", None}:
                        frontmatter[current_key] = [entry]
                    else:
                        frontmatter[current_key] = [existing, entry]
                    continue
                if ":" not in raw_line:
                    current_key = ""
                    continue
                key, value = raw_line.split(":", 1)
                current_key = key.strip()
                frontmatter[current_key] = parse_scalar(value.strip())
            body = "\n".join(lines[index + 1 :])
            return frontmatter, body

    return {}, text


def parse_scalar(value: str) -> object:
    if not value:
        return ""
    lower = value.lower()
    if lower == "true":
        return True
    if lower == "false":
        return False
    if value.isdigit():
        return int(value)
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    return value


def normalize_key(value: str) -> str:
    cleaned = value.strip().replace("\\", "/")
    cleaned = cleaned.split("#", 1)[0]
    cleaned = cleaned.removesuffix(".md").removesuffix(".html")
    cleaned = cleaned.strip("/")
    return cleaned.lower()


def normalize_asset_key(value: str) -> str:
    cleaned = value.strip().replace("\\", "/")
    cleaned = cleaned.split("#", 1)[0]
    cleaned = cleaned.strip("/")
    return cleaned.lower()


def strip_markdown(text: str) -> str:
    frontmatter, body = strip_frontmatter(text)
    _ = frontmatter
    body = re.sub(r"```.*?```", " ", body, flags=re.S)
    body = re.sub(r"`([^`]+)`", r"\1", body)
    body = re.sub(r"!\[[^\]]*\]\(([^)]+)\)", " ", body)
    body = re.sub(r"\[\[([^\]]+)\]\]", r"\1", body)
    body = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1", body)
    body = re.sub(r"[#>*_|-]+", " ", body)
    return re.sub(r"\s+", " ", body).strip()


def extract_title(rel_path: Path, body: str, frontmatter: dict[str, object]) -> str:
    fallback_stem = rel_path.stem
    if ", " in fallback_stem:
        fallback_stem = fallback_stem.split(", ", 1)[1]
    fallback_stem = re.sub(r"\s+\((latest|full)\)$", "", fallback_stem, flags=re.I).strip()

    if isinstance(frontmatter.get("title"), str) and frontmatter["title"].strip():
        return str(frontmatter["title"]).strip()
    for line in body.splitlines():
        match = HEADING_RE.match(line)
        if match:
            candidate = match.group(2).strip()
            if normalize_key(candidate) in {
                "question",
                "answer",
                "response",
                "assistant",
                "user",
                "分析结果",
                "分析结论",
            }:
                return fallback_stem or candidate
            return candidate
    return fallback_stem or rel_path.stem


def format_date_label(path: Path, frontmatter: dict[str, object]) -> str:
    if isinstance(frontmatter.get("date"), str) and frontmatter["date"].strip():
        return str(frontmatter["date"]).strip()
    return os.path.getmtime(path).__format__(".0f")


def safe_date_label(path: Path, frontmatter: dict[str, object]) -> str:
    if isinstance(frontmatter.get("date"), str) and frontmatter["date"].strip():
        return str(frontmatter["date"]).strip()
    return __import__("datetime").datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d")


def slugify(text: str, used: set[str]) -> str:
    slug = re.sub(r"[^\w\u4e00-\u9fff\- ]+", "", text, flags=re.UNICODE).strip().lower()
    slug = re.sub(r"\s+", "-", slug).strip("-")
    if not slug:
        slug = "section"
    candidate = slug
    counter = 2
    while candidate in used:
        candidate = f"{slug}-{counter}"
        counter += 1
    used.add(candidate)
    return candidate


def build_asset_lookup(assets: list[Path]) -> dict[str, Path]:
    asset_buckets: dict[str, list[Path]] = {}
    for asset in assets:
        rel = asset.relative_to(VAULT_ROOT)
        aliases = {
            normalize_asset_key(rel.as_posix()),
            normalize_asset_key(rel.name),
            normalize_asset_key(rel.stem),
        }
        for alias in aliases:
            if alias:
                asset_buckets.setdefault(alias, []).append(rel)
    return {
        alias: bucket[0]
        for alias, bucket in asset_buckets.items()
        if len(bucket) == 1
    }


def resolve_local_asset(target: str, current_note: Note, asset_lookup: dict[str, Path]) -> Path | None:
    clean_target = target.split("#", 1)[0].strip()
    if not clean_target or urlparse(clean_target).scheme:
        return None
    candidate = (current_note.rel_path.parent / clean_target).resolve()
    try:
        rel = candidate.relative_to(VAULT_ROOT.resolve())
    except ValueError:
        rel = None
    if rel is not None:
        local_path = VAULT_ROOT / rel
        if local_path.exists() and local_path.suffix.lower() in ASSET_EXTENSIONS:
            return rel

    if clean_target.startswith("/"):
        prefixed = normalize_asset_key(clean_target.lstrip("/"))
        if prefixed in asset_lookup:
            return asset_lookup[prefixed]

    return asset_lookup.get(normalize_asset_key(clean_target))


def resolve_note_reference(target: str, current_note: Note | None, note_lookup: dict[str, Note], alias_lookup: dict[str, Note]) -> Note | None:
    clean_target = target.split("#", 1)[0].strip()
    if not clean_target:
        return None

    if clean_target.startswith("/"):
        note = note_lookup.get(normalize_key(clean_target))
        if note:
            return note

    if current_note is not None:
        relative_candidate = normalize_key((current_note.rel_path.parent / clean_target).as_posix())
        if relative_candidate in note_lookup:
            return note_lookup[relative_candidate]

    normalized = normalize_key(clean_target)
    if normalized in note_lookup:
        return note_lookup[normalized]
    return alias_lookup.get(normalized)


class MarkdownRenderer:
    def __init__(self, note_lookup: dict[str, Note], alias_lookup: dict[str, Note], asset_lookup: dict[str, Path]) -> None:
        self.note_lookup = note_lookup
        self.alias_lookup = alias_lookup
        self.asset_lookup = asset_lookup

    def render(self, note: Note) -> tuple[str, list[Heading], set[str], str]:
        used_anchors: set[str] = set()
        links_to: set[str] = set()
        html_body, headings = self.render_blocks(note.body_markdown.splitlines(), note, used_anchors, links_to, collect_headings=True)
        properties_html = self.render_note_properties(note, links_to)
        return html_body, headings, links_to, properties_html

    @staticmethod
    def property_icon_svg(key: str) -> str:
        kind = key.lower()
        if kind in {"published", "created", "date", "updated"}:
            return (
                '<svg viewBox="0 0 24 24" aria-hidden="true">'
                '<rect x="3" y="4" width="18" height="17" rx="2"></rect>'
                '<path d="M8 2v4M16 2v4M3 10h18"></path>'
                "</svg>"
            )
        if kind in {"tags", "tag"}:
            return (
                '<svg viewBox="0 0 24 24" aria-hidden="true">'
                '<path d="M20.59 13.41 11 3.83A2 2 0 0 0 9.59 3H4a1 1 0 0 0-1 1v5.59A2 2 0 0 0 3.83 11l9.58 9.59a2 2 0 0 0 2.83 0l4.35-4.35a2 2 0 0 0 0-2.83Z"></path>'
                '<circle cx="7.5" cy="7.5" r="1.2"></circle>'
                "</svg>"
            )
        if kind in {"source", "url", "link"}:
            return (
                '<svg viewBox="0 0 24 24" aria-hidden="true">'
                '<path d="M10 13a5 5 0 0 0 7.07 0l2.83-2.83a5 5 0 0 0-7.07-7.07L11 4"></path>'
                '<path d="M14 11a5 5 0 0 0-7.07 0L4.1 13.83a5 5 0 0 0 7.07 7.07L13 20"></path>'
                "</svg>"
            )
        return (
            '<svg viewBox="0 0 24 24" aria-hidden="true">'
            '<path d="M5 7h14M5 12h14M5 17h14"></path>'
            "</svg>"
        )

    @staticmethod
    def property_sort_key(item: tuple[str, object]) -> tuple[int, str]:
        key = item[0]
        try:
            return PROPERTY_ORDER.index(key), key
        except ValueError:
            return len(PROPERTY_ORDER), key

    @staticmethod
    def clean_property_values(value: object) -> list[object]:
        if isinstance(value, list):
            return [item for item in value if not (isinstance(item, str) and not item.strip())]
        if isinstance(value, str) and not value.strip():
            return []
        if value is None:
            return []
        return [value]

    def render_note_properties(self, note: Note, links_to: set[str]) -> str:
        if not note.frontmatter:
            return ""

        property_items: list[tuple[str, object]] = [("title", note.title)]
        property_items.extend(
            (key, value)
            for key, value in sorted(note.frontmatter.items(), key=self.property_sort_key)
            if key not in {"title", "publish"}
        )

        rows: list[str] = []
        for key, raw_value in property_items:
            rows.append(
                '<div class="note-property-row">'
                f'<span class="note-property-icon">{self.property_icon_svg(key)}</span>'
                f'<span class="note-property-name">{html.escape(PROPERTY_LABELS.get(key, key))}</span>'
                f'<div class="note-property-value">{self.render_property_value(key, raw_value, note, links_to)}</div>'
                "</div>"
            )

        return (
            '<section class="note-properties">'
            '<h2 class="note-properties-title">笔记属性</h2>'
            '<div class="note-properties-grid">'
            + "".join(rows)
            + "</div></section>"
        )

    def render_property_value(self, key: str, value: object, note: Note, links_to: set[str]) -> str:
        cleaned_values = self.clean_property_values(value)
        if not cleaned_values:
            return '<span class="note-property-empty">—</span>'

        if key == "tags":
            tags = []
            for entry in cleaned_values:
                tag_text = str(entry).strip().lstrip("#")
                if tag_text:
                    tags.append(f'<span class="note-property-tag">{html.escape(tag_text)}</span>')
            return "".join(tags) if tags else '<span class="note-property-empty">—</span>'

        if len(cleaned_values) == 1:
            return self.render_property_scalar(str(cleaned_values[0]), note, links_to)

        items = []
        for entry in cleaned_values:
            items.append(f'<div class="note-property-list-item">{self.render_property_scalar(str(entry), note, links_to)}</div>')
        return '<div class="note-property-list">' + "".join(items) + "</div>"

    def render_property_scalar(self, value: str, note: Note, links_to: set[str]) -> str:
        stripped = value.strip()
        wiki_match = WIKI_LINK_RE.fullmatch(stripped)
        if wiki_match:
            target = wiki_match.group(2)
            label = wiki_match.group(4) or target
            target_note = resolve_note_reference(target, note, self.note_lookup, self.alias_lookup)
            if target_note is not None:
                links_to.add(target_note.note_key)
                href = relative_href(note.output_path, target_note.output_path)
                return f'<a href="{href}">{html.escape(label)}</a>'
            return html.escape(label)
        parsed = urlparse(stripped)
        if parsed.scheme in {"http", "https", "mailto"}:
            attrs = ' target="_blank" rel="noreferrer"' if parsed.scheme in {"http", "https"} else ""
            return f'<a class="note-property-link" href="{html.escape(stripped, quote=True)}"{attrs}>{html.escape(stripped)}</a>'
        return self.render_inline(stripped, note, links_to)

    @staticmethod
    def render_media_embed(src: str, alt_text: str, suffix: str, *, caption: str = "") -> str:
        escaped_src = html.escape(src, quote=True)
        escaped_alt = html.escape(alt_text)
        trimmed_caption = caption.strip()
        caption_html = f'<span class="asset-caption">{html.escape(trimmed_caption)}</span>' if trimmed_caption else ""
        if suffix in IMAGE_EXTENSIONS:
            return (
                '<span class="asset-embed asset-embed-image">'
                f'<img class="doc-image" src="{escaped_src}" alt="{escaped_alt}" loading="lazy">'
                f"{caption_html}"
                "</span>"
            )
        if suffix in VIDEO_EXTENSIONS:
            return (
                '<span class="asset-embed asset-embed-video">'
                f'<video controls preload="metadata" src="{escaped_src}"></video>'
                f"{caption_html}"
                "</span>"
            )
        if suffix in AUDIO_EXTENSIONS:
            return (
                '<span class="asset-embed asset-embed-audio">'
                f'<audio controls preload="metadata" src="{escaped_src}"></audio>'
                f"{caption_html}"
                "</span>"
            )
        return f'<a class="asset-link" href="{escaped_src}">{html.escape(trimmed_caption or alt_text or "查看附件")}</a>'

    def render_blocks(
        self,
        lines: list[str],
        note: Note,
        used_anchors: set[str],
        links_to: set[str],
        *,
        collect_headings: bool,
    ) -> tuple[str, list[Heading]]:
        chunks: list[str] = []
        headings: list[Heading] = []
        index = 0

        while index < len(lines):
            line = lines[index]
            stripped = line.strip()

            if not stripped:
                index += 1
                continue

            if self.is_fence_start(line):
                block_html, index = self.render_fence(lines, index)
                chunks.append(block_html)
                continue

            if HR_RE.match(line):
                chunks.append("<hr>")
                index += 1
                continue

            heading_match = HEADING_RE.match(line)
            if heading_match:
                level = len(heading_match.group(1))
                text = heading_match.group(2).strip()
                anchor = slugify(text, used_anchors)
                block = f'<h{level} id="{anchor}">{self.render_inline(text, note, links_to)}</h{level}>'
                chunks.append(block)
                if collect_headings:
                    headings.append(Heading(level=level, text=text, anchor=anchor))
                index += 1
                continue

            if line.lstrip().startswith(">"):
                block_html, index = self.render_blockquote(lines, index, note, used_anchors, links_to)
                chunks.append(block_html)
                continue

            if self.is_table_start(lines, index):
                block_html, index = self.render_table(lines, index, note, links_to)
                chunks.append(block_html)
                continue

            if LIST_ITEM_RE.match(line):
                block_html, index = self.render_list(lines, index, note, used_anchors, links_to)
                chunks.append(block_html)
                continue

            block_html, index = self.render_paragraph(lines, index, note, links_to)
            chunks.append(block_html)

        return "\n".join(chunks), headings

    @staticmethod
    def is_fence_start(line: str) -> bool:
        stripped = line.lstrip()
        return stripped.startswith("```") or stripped.startswith("~~~")

    @staticmethod
    def is_table_start(lines: list[str], index: int) -> bool:
        if index + 1 >= len(lines):
            return False
        return "|" in lines[index] and TABLE_SEPARATOR_RE.match(lines[index + 1]) is not None

    def render_fence(self, lines: list[str], index: int) -> tuple[str, int]:
        opener = lines[index].lstrip()
        fence_char = opener[0]
        fence_len = len(opener) - len(opener.lstrip(fence_char))
        info = opener[fence_len:].strip()
        code_lines: list[str] = []
        index += 1

        while index < len(lines):
            candidate = lines[index].lstrip()
            if candidate.startswith(fence_char * fence_len):
                index += 1
                break
            code_lines.append(lines[index])
            index += 1

        language_name = info.split()[0] if info else ""
        raw_code = "\n".join(code_lines)
        code_html = highlight_code_html(raw_code, language_name)
        language_attr = ""
        code_class = ""
        language_label = "code"
        if language_name:
            escaped_language = html.escape(language_name)
            language_attr = f' data-language="{escaped_language}"'
            code_class = f' class="language-{escaped_language}"'
            language_label = escaped_language
        copy_button = (
            '<button class="code-copy-button" type="button" aria-label="Copy code" title="Copy">'
            '<svg viewBox="0 0 24 24" aria-hidden="true">'
            '<rect x="9" y="9" width="10" height="10" rx="2"></rect>'
            '<path d="M15 9V7a2 2 0 0 0-2-2H7a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2h2"></path>'
            '</svg>'
            '</button>'
        )
        toolbar = (
            '<span class="code-block-toolbar">'
            f'<span class="code-block-language">{language_label}</span>'
            f"{copy_button}"
            "</span>"
        )
        return f"<pre{language_attr}>{toolbar}<code{code_class}>{code_html}</code></pre>", index

    def render_blockquote(
        self,
        lines: list[str],
        index: int,
        note: Note,
        used_anchors: set[str],
        links_to: set[str],
    ) -> tuple[str, int]:
        quote_lines: list[str] = []
        while index < len(lines):
            line = lines[index]
            if not line.strip():
                quote_lines.append("")
                index += 1
                continue
            if not line.lstrip().startswith(">"):
                break
            quote_lines.append(re.sub(r"^\s*> ?", "", line, count=1))
            index += 1
        inner_html, _ = self.render_blocks(quote_lines, note, used_anchors, links_to, collect_headings=False)
        return f"<blockquote>{inner_html}</blockquote>", index

    def render_table(self, lines: list[str], index: int, note: Note, links_to: set[str]) -> tuple[str, int]:
        header = self.split_table_row(lines[index])
        index += 2
        body_rows: list[list[str]] = []
        while index < len(lines):
            if not lines[index].strip() or "|" not in lines[index]:
                break
            body_rows.append(self.split_table_row(lines[index]))
            index += 1

        head_html = "".join(f"<th>{self.render_inline(cell, note, links_to)}</th>" for cell in header)
        body_html = []
        for row in body_rows:
            cells = "".join(f"<td>{self.render_inline(cell, note, links_to)}</td>" for cell in row)
            body_html.append(f"<tr>{cells}</tr>")
        return (
            "<table><thead><tr>"
            + head_html
            + "</tr></thead><tbody>"
            + "".join(body_html)
            + "</tbody></table>",
            index,
        )

    @staticmethod
    def split_table_row(line: str) -> list[str]:
        trimmed = line.strip().strip("|")
        return [cell.strip() for cell in trimmed.split("|")]

    def render_list(
        self,
        lines: list[str],
        index: int,
        note: Note,
        used_anchors: set[str],
        links_to: set[str],
    ) -> tuple[str, int]:
        html_out, next_index = self.render_list_items(lines, index, note, used_anchors, links_to, base_indent=self.indent_width(lines[index]))
        return html_out, next_index

    def render_list_items(
        self,
        lines: list[str],
        index: int,
        note: Note,
        used_anchors: set[str],
        links_to: set[str],
        *,
        base_indent: int,
    ) -> tuple[str, int]:
        items: list[str] = []
        list_tag = ""

        while index < len(lines):
            line = lines[index]
            if not line.strip():
                index += 1
                continue

            match = LIST_ITEM_RE.match(line)
            if not match:
                break

            indent = self.indent_width(match.group("indent"))
            if indent < base_indent:
                break
            if indent > base_indent:
                nested_html, index = self.render_list_items(lines, index, note, used_anchors, links_to, base_indent=indent)
                if items:
                    items[-1] = items[-1][:-5] + nested_html + "</li>"
                continue

            marker = match.group("marker")
            current_tag = "ol" if marker.endswith(".") else "ul"
            if not list_tag:
                list_tag = current_tag
            elif current_tag != list_tag:
                break

            content_lines = [match.group("content")]
            index += 1

            while index < len(lines):
                next_line = lines[index]
                if not next_line.strip():
                    lookahead = index + 1
                    while lookahead < len(lines) and not lines[lookahead].strip():
                        lookahead += 1
                    if lookahead >= len(lines):
                        index = lookahead
                        break
                    upcoming = lines[lookahead]
                    upcoming_match = LIST_ITEM_RE.match(upcoming)
                    upcoming_indent = self.indent_width(upcoming)
                    if upcoming_match and self.indent_width(upcoming_match.group("indent")) <= base_indent:
                        index = lookahead
                        break
                    if upcoming_indent <= base_indent and not upcoming.startswith((" ", "\t")):
                        index = lookahead
                        break
                    content_lines.append("")
                    index += 1
                    continue

                next_match = LIST_ITEM_RE.match(next_line)
                next_indent = self.indent_width(next_line)
                if next_match and self.indent_width(next_match.group("indent")) == base_indent:
                    break
                if next_match and self.indent_width(next_match.group("indent")) < base_indent:
                    break
                if self.starts_new_block(lines, index, base_indent):
                    break
                if next_match and self.indent_width(next_match.group("indent")) > base_indent:
                    nested_html, index = self.render_list_items(
                        lines,
                        index,
                        note,
                        used_anchors,
                        links_to,
                        base_indent=self.indent_width(next_match.group("indent")),
                    )
                    content_lines.append(f"@@HTML_BLOCK@@{nested_html}")
                    continue

                trimmed = next_line[base_indent + 2 :] if len(next_line) > base_indent + 2 else next_line.lstrip()
                content_lines.append(trimmed)
                index += 1

            item_segments: list[str] = []
            buffer: list[str] = []
            for entry in content_lines:
                if entry.startswith("@@HTML_BLOCK@@"):
                    if buffer:
                        fragment, _ = self.render_blocks(buffer, note, used_anchors, links_to, collect_headings=False)
                        item_segments.append(self.unwrap_paragraph(fragment))
                        buffer = []
                    item_segments.append(entry.replace("@@HTML_BLOCK@@", "", 1))
                else:
                    buffer.append(entry)
            if buffer:
                fragment, _ = self.render_blocks(buffer, note, used_anchors, links_to, collect_headings=False)
                item_segments.append(self.unwrap_paragraph(fragment))
            items.append("<li>" + "".join(item_segments) + "</li>")

        if not list_tag:
            return "", index
        return f"<{list_tag}>" + "".join(items) + f"</{list_tag}>", index

    @staticmethod
    def unwrap_paragraph(fragment: str) -> str:
        stripped = fragment.strip()
        if stripped.startswith("<p>") and stripped.endswith("</p>") and stripped.count("<p>") == 1:
            return stripped[3:-4]
        return fragment

    def render_paragraph(self, lines: list[str], index: int, note: Note, links_to: set[str]) -> tuple[str, int]:
        paragraph_lines: list[str] = []
        while index < len(lines):
            line = lines[index]
            if not line.strip():
                break
            if self.is_fence_start(line) or HR_RE.match(line) or HEADING_RE.match(line):
                break
            if line.lstrip().startswith(">") or LIST_ITEM_RE.match(line) or self.is_table_start(lines, index):
                break
            paragraph_lines.append(line.strip())
            index += 1
        joined = " ".join(paragraph_lines)
        return f"<p>{self.render_inline(joined, note, links_to)}</p>", index

    def starts_new_block(self, lines: list[str], index: int, base_indent: int) -> bool:
        line = lines[index]
        if self.indent_width(line) > base_indent:
            return False
        return bool(
            self.is_fence_start(line)
            or HR_RE.match(line)
            or HEADING_RE.match(line)
            or line.lstrip().startswith(">")
            or self.is_table_start(lines, index)
        )

    def render_inline(self, text: str, note: Note, links_to: set[str]) -> str:
        placeholders: dict[str, str] = {}

        def take_placeholder(value: str) -> str:
            token = f"@@INLINE_{len(placeholders)}@@"
            placeholders[token] = value
            return token

        def replace_code(match: re.Match[str]) -> str:
            code = html.escape(match.group(2))
            return take_placeholder(f"<code>{code}</code>")

        text = INLINE_CODE_RE.sub(replace_code, text)
        escaped = html.escape(text)

        def replace_wiki(match: re.Match[str]) -> str:
            is_embed = bool(match.group(1))
            target = html.unescape(match.group(2))
            anchor = html.unescape(match.group(3) or "")
            label = html.unescape(match.group(4) or target)
            asset_rel = resolve_local_asset(target, note, self.asset_lookup)
            if asset_rel is not None:
                href = relative_href(note.output_path, DIST_ROOT / asset_rel)
                if is_embed:
                    caption = label if label != target else ""
                    return take_placeholder(self.render_media_embed(href, label or asset_rel.stem, asset_rel.suffix.lower(), caption=caption))
                return take_placeholder(f'<a class="asset-link" href="{href}">{html.escape(label)}</a>')
            target_note = resolve_note_reference(target, note, self.note_lookup, self.alias_lookup)
            if target_note:
                links_to.add(target_note.note_key)
                href = relative_href(note.output_path, target_note.output_path)
                if anchor:
                    href += "#" + quote(anchor)
                if is_embed:
                    return take_placeholder(f'<div class="asset-link"><a href="{href}">嵌入：{html.escape(label)}</a></div>')
                return take_placeholder(f'<a href="{href}">{html.escape(label)}</a>')
            return html.escape(match.group(0))

        escaped = WIKI_LINK_RE.sub(replace_wiki, escaped)

        def replace_md_link(match: re.Match[str]) -> str:
            is_image = bool(match.group(1))
            label = html.unescape(match.group(2))
            target = html.unescape(match.group(3)).strip()
            parsed = urlparse(target)
            if parsed.scheme in {"http", "https", "mailto"}:
                if is_image:
                    suffix = Path(parsed.path).suffix.lower()
                    return take_placeholder(self.render_media_embed(target, label or "image", suffix))
                attrs = ' target="_blank" rel="noreferrer"' if parsed.scheme in {"http", "https"} else ""
                return take_placeholder(f'<a href="{html.escape(target, quote=True)}"{attrs}>{html.escape(label)}</a>')

            asset_rel = resolve_local_asset(target, note, self.asset_lookup)
            if asset_rel is not None:
                href = relative_href(note.output_path, DIST_ROOT / asset_rel)
                if is_image:
                    return take_placeholder(self.render_media_embed(href, label or asset_rel.stem, asset_rel.suffix.lower()))
                return take_placeholder(f'<a class="asset-link" href="{href}">{html.escape(label)}</a>')

            target_note = resolve_note_reference(target, note, self.note_lookup, self.alias_lookup)
            if target_note:
                links_to.add(target_note.note_key)
                href = relative_href(note.output_path, target_note.output_path)
                return take_placeholder(f'<a href="{href}">{html.escape(label)}</a>')

            if is_image:
                return html.escape(match.group(0))
            return take_placeholder(f'<a href="{html.escape(target, quote=True)}">{html.escape(label)}</a>')

        escaped = MD_LINK_RE.sub(replace_md_link, escaped)
        escaped = BOLD_RE.sub(lambda match: f"<strong>{match.group(2)}</strong>", escaped)
        escaped = ITALIC_RE.sub(lambda match: f"<em>{match.group(1)}</em>", escaped)

        for token, replacement in placeholders.items():
            escaped = escaped.replace(token, replacement)
        return escaped

    @staticmethod
    def indent_width(value: str) -> int:
        expanded = value.expandtabs(2)
        return len(expanded) - len(expanded.lstrip(" "))


def relative_href(current_output: Path, target_output: Path) -> str:
    return os.path.relpath(target_output, current_output.parent).replace(os.sep, "/")


def build_alias_lookup(notes: list[Note]) -> tuple[dict[str, Note], dict[str, Note]]:
    note_lookup = {note.note_key: note for note in notes}
    alias_buckets: dict[str, list[Note]] = {}
    for note in notes:
        aliases = {
            normalize_key(note.rel_path.stem),
            normalize_key(note.rel_path.as_posix()),
            normalize_key(note.title),
        }
        for alias in aliases:
            if alias:
                alias_buckets.setdefault(alias, []).append(note)
    alias_lookup = {
        alias: bucket[0]
        for alias, bucket in alias_buckets.items()
        if len(bucket) == 1
    }
    return note_lookup, alias_lookup


def build_tree(notes: list[Note]) -> FolderNode:
    root = FolderNode(name=SITE_NAME, rel_path=Path("."))
    for note in notes:
        node = root
        for part in note.rel_path.parts[:-1]:
            next_rel = node.rel_path / part if node.rel_path != Path(".") else Path(part)
            node = node.children.setdefault(part, FolderNode(name=part, rel_path=next_rel))
        node.notes.append(note)
    return root


def folder_index_rel_path(folder: Path) -> Path:
    if folder == Path("."):
        return Path("index.html")
    return folder / "index.html"


def folder_index_output(folder: Path) -> Path:
    return DIST_ROOT / folder_index_rel_path(folder)


def ensure_dist() -> None:
    if DIST_ROOT.exists():
        shutil.rmtree(DIST_ROOT)
    (DIST_ROOT / "assets").mkdir(parents=True, exist_ok=True)


def write_assets(search_index: list[dict[str, str]]) -> None:
    (DIST_ROOT / "assets" / "site.css").write_text(STYLE_CSS, encoding="utf-8")
    (DIST_ROOT / "assets" / "app.js").write_text(APP_JS, encoding="utf-8")
    search_js = "window.__PUBLISH_SEARCH_INDEX = " + json.dumps(search_index, ensure_ascii=False, separators=(",", ":")) + ";"
    (DIST_ROOT / "assets" / "search-index.js").write_text(search_js, encoding="utf-8")
    (DIST_ROOT / ".nojekyll").write_text("", encoding="utf-8")


def copy_assets(assets: list[Path]) -> None:
    for asset in assets:
        rel = asset.relative_to(VAULT_ROOT)
        target = DIST_ROOT / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(asset, target)


def sort_notes(notes: list[Note]) -> list[Note]:
    return sorted(notes, key=lambda note: note.title.lower())


def breadcrumb_html(current_output: Path, rel_path: Path) -> str:
    crumbs = [f'<a href="{relative_href(current_output, folder_index_output(Path(".")))}">START HERE</a>']
    current = Path(".")
    for part in rel_path.parts:
        current = current / part if current != Path(".") else Path(part)
        crumbs.append("<span>/</span>")
        crumbs.append(f'<a href="{relative_href(current_output, folder_index_output(current))}">{html.escape(part)}</a>')
    return "".join(crumbs)


def versioned_asset_href(current_output: Path, asset_path: Path) -> str:
    href = relative_href(current_output, asset_path)
    if asset_path.exists():
        return f"{href}?v={asset_path.stat().st_mtime_ns}"
    return href


def page_shell(
    *,
    title: str,
    current_output: Path,
    nav_html: str,
    aside_html: str,
    content_html: str,
    mobile_title: str,
    is_home: bool = False,
) -> str:
    css_href = versioned_asset_href(current_output, DIST_ROOT / "assets" / "site.css")
    app_href = versioned_asset_href(current_output, DIST_ROOT / "assets" / "app.js")
    search_href = versioned_asset_href(current_output, DIST_ROOT / "assets" / "search-index.js")
    body_class = "page-home" if is_home else "page-doc"
    root_prefix = os.path.relpath(DIST_ROOT, current_output.parent).replace(os.sep, "/")
    if root_prefix == ".":
        root_prefix = ""
    elif not root_prefix.endswith("/"):
        root_prefix += "/"
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)} · {html.escape(SITE_NAME)}</title>
  <link rel="stylesheet" href="{css_href}">
</head>
<body class="theme-light {body_class}" data-root-prefix="{root_prefix}">
  <div class="mobile-bar">
    <button class="mobile-menu" type="button" aria-label="打开导航">☰</button>
    <div class="mobile-title">{html.escape(mobile_title)}</div>
  </div>
  <div class="published-container has-navigation is-readable-line-width">
    <div class="site-body">
      <aside class="site-nav site-body-left-column">
        {nav_html}
      </aside>
      <div class="site-body-center-column">
        <main class="site-main publish-renderer">
          <div class="site-content markdown-preview-view markdown-rendered">
            <div class="markdown-preview-sizer">
              {content_html}
            </div>
          </div>
        </main>
      </div>
    </div>
    <footer class="site-footer">
      <a href="https://obsidian.md/publish" target="_blank" rel="noreferrer">Powered by Obsidian Publish</a>
    </footer>
  </div>
  <div class="scrim"></div>
  <script src="{search_href}"></script>
  <script src="{app_href}"></script>
</body>
</html>
"""


def nav_html(current_output: Path, tree: FolderNode, *, active_note: Note | None = None, active_folder: Path | None = None, active_home: bool = False) -> str:
    home_href = relative_href(current_output, folder_index_output(Path(".")))
    header = f"""
    <div class="site-body-left-column-inner">
      <a class="nav-site-title site-body-left-column-site-name" href="{home_href}">{html.escape(SITE_NAME)}</a>
      <div class="site-body-left-column-site-theme-toggle">
        <button class="theme-toggle checkbox-container" type="button" aria-label="切换明暗模式">
          <span class="option mod-dark" aria-hidden="true">
            <svg viewBox="0 0 24 24">
              <circle cx="12" cy="12" r="4"></circle>
              <path d="M12 2v2.4M12 19.6V22M4.93 4.93l1.7 1.7M17.37 17.37l1.7 1.7M2 12h2.4M19.6 12H22M4.93 19.07l1.7-1.7M17.37 6.63l1.7-1.7"></path>
            </svg>
          </span>
          <span class="option mod-light" aria-hidden="true">
            <svg viewBox="0 0 24 24">
              <path d="M20 15.2A7.9 7.9 0 0 1 8.8 4 8.9 8.9 0 1 0 20 15.2Z"></path>
            </svg>
          </span>
        </button>
      </div>
      <div class="nav-search-wrap">
        <input class="nav-search" type="search" placeholder="Search page or heading...">
        <div class="search-results"></div>
      </div>
    """
    body = ['<div class="nav-tree nav-view-outer"><div class="nav-view">']
    body.append('<div class="tree-section">')
    body.append(f'<a class="tree-home-link{" is-active" if active_home else ""}" href="{home_href}">START HERE</a>')
    body.append("</div>")
    for folder in sorted(tree.children.values(), key=lambda item: item.name.lower()):
        body.append(render_folder_node(current_output, folder, active_note=active_note, active_folder=active_folder))
    for note in sort_notes(tree.notes):
        note_href = relative_href(current_output, note.output_path)
        active = active_note is not None and note.note_key == active_note.note_key
        body.append(f'<a class="tree-note-link{" is-active" if active else ""}" href="{note_href}">{html.escape(note.title)}</a>')
    body.append("</div></div></div>")
    return header + "".join(body)


def render_folder_node(current_output: Path, folder: FolderNode, *, active_note: Note | None, active_folder: Path | None) -> str:
    folder_output = folder_index_output(folder.rel_path)
    folder_href = relative_href(current_output, folder_output)
    note_in_folder = active_note is not None and active_note.rel_path.as_posix().startswith(folder.rel_path.as_posix())
    folder_active = active_folder is not None and active_folder == folder.rel_path
    expanded = note_in_folder or folder_active or len(folder.rel_path.parts) <= 1
    header_class = "" if expanded else " is-collapsed"
    children_class = "" if expanded else " is-hidden"
    current_flag = " is-active" if folder_active else ""
    chunks = [
        '<div class="tree-folder">',
        f'<div class="tree-folder-header{header_class}">',
        f'<button class="tree-toggle" type="button" aria-expanded="{str(expanded).lower()}" aria-label="展开或收起文件夹">▾</button>',
        f'<a class="tree-folder-link{current_flag}" href="{folder_href}">{html.escape(folder.name)}</a>',
        '</div>',
        f'<div class="tree-children{children_class}">',
    ]
    for child in sorted(folder.children.values(), key=lambda item: item.name.lower()):
        chunks.append(render_folder_node(current_output, child, active_note=active_note, active_folder=active_folder))
    for note in sort_notes(folder.notes):
        note_href = relative_href(current_output, note.output_path)
        active = active_note is not None and note.note_key == active_note.note_key
        chunks.append(f'<a class="tree-note-link{" is-active" if active else ""}" href="{note_href}">{html.escape(note.title)}</a>')
    chunks.append("</div></div>")
    return "".join(chunks)


def build_toc(note: Note, current_output: Path) -> str:
    headings = [heading for heading in note.headings if heading.level >= 2]
    if not headings and note.headings:
        headings = note.headings
    if not headings:
        return '<div class="aside-card"><h2 class="aside-title">页内目录</h2><div class="empty-hint">当前文档没有可折叠的目录。</div></div>'
    items = []
    for heading in headings:
        items.append(
            f'<li class="toc-item" data-level="{heading.level}"><a class="toc-link" href="#{heading.anchor}">{html.escape(heading.text)}</a></li>'
        )
    return '<div class="aside-card"><h2 class="aside-title">页内目录</h2><ul class="toc-list">' + "".join(items) + "</ul></div>"


def build_backlinks(note: Note, current_output: Path) -> str:
    if not note.backlinks:
        return '<div class="aside-card"><h2 class="aside-title">关联文档</h2><div class="empty-hint">当前没有其他已发布文档链接到这篇笔记。</div></div>'
    items = []
    for backlink in sorted(note.backlinks, key=lambda item: item.title.lower()):
        href = relative_href(current_output, backlink.output_path)
        items.append(f'<li><a class="backlink-link" href="{href}">{html.escape(backlink.title)}</a></li>')
    return '<div class="aside-card"><h2 class="aside-title">关联文档</h2><ul class="backlink-list">' + "".join(items) + "</ul></div>"


def build_home_aside(notes: list[Note], current_output: Path) -> str:
    latest = sorted(notes, key=lambda note: note.mtime, reverse=True)[:8]
    items = [
        f'<li><a class="mini-link" href="{relative_href(current_output, note.output_path)}">{html.escape(note.title)}</a></li>'
        for note in latest
    ]
    return (
        '<div class="aside-card"><h2 class="aside-title">最近更新</h2><ul class="mini-list">'
        + "".join(items)
        + "</ul></div>"
    )


def unique_labels(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        cleaned = value.strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        result.append(cleaned)
    return result


def shorten_label(text: str, limit: int = 24) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def plain_meta_text(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        return ""
    wiki_match = WIKI_LINK_RE.fullmatch(stripped)
    if wiki_match:
        return (wiki_match.group(4) or wiki_match.group(2) or "").strip()
    md_match = MD_LINK_RE.fullmatch(stripped)
    if md_match:
        return (md_match.group(2) or md_match.group(3) or "").strip()
    return stripped


def note_meta_html(note: Note) -> str:
    parts: list[str] = []

    author_value = note.frontmatter.get("author")
    author_items = author_value if isinstance(author_value, list) else ([author_value] if author_value else [])
    author_items = [plain_meta_text(str(item)) for item in author_items if str(item).strip()]
    if author_items:
        parts.append("Author: " + html.escape(" · ".join(author_items)))

    source_value = note.frontmatter.get("source")
    if isinstance(source_value, str) and source_value.strip():
        source_text = source_value.strip()
        parsed = urlparse(source_text)
        if parsed.scheme in {"http", "https", "mailto"}:
            attrs = ' target="_blank" rel="noreferrer"' if parsed.scheme in {"http", "https"} else ""
            parts.append(
                "Source: "
                + f'<a href="{html.escape(source_text, quote=True)}"{attrs}>{html.escape(source_text)}</a>'
            )
        else:
            parts.append("Source: " + html.escape(plain_meta_text(source_text)))

    if not parts:
        folder_path = note.rel_path.parent.as_posix() if note.rel_path.parent != Path(".") else "Vault Root"
        parts.append(f"Path: {html.escape(folder_path)}")
        parts.append(f"Updated: {html.escape(note.date_label)}")

    return "".join(f'<span class="article-meta-line">{part}</span>' for part in parts)


def build_note_page(note: Note, tree: FolderNode) -> str:
    breadcrumbs = breadcrumb_html(note.output_path, note.rel_path.parent)
    body_html = note.html_body
    if note.headings and note.headings[0].level == 1 and note.headings[0].text == note.title:
        body_html = re.sub(r"^\s*<h1 id=\"[^\"]+\">.*?</h1>\s*", "", body_html, count=1, flags=re.S)
        body_html = re.sub(r"^\s*<hr>\s*", "", body_html, count=1, flags=re.S)
    content = f"""
    <div class="breadcrumbs">{breadcrumbs}</div>
    <h1 class="page-header">{html.escape(note.title)}</h1>
    <div class="article-meta">{note_meta_html(note)}</div>
    <div class="doc-body">
      {body_html}
    </div>
    """
    return page_shell(
        title=note.title,
        current_output=note.output_path,
        nav_html=nav_html(note.output_path, tree, active_note=note),
        aside_html="",
        content_html=content,
        mobile_title=note.title,
    )


def build_summary(
    text: str,
    *,
    title: str | None = None,
    fallback: str = "这是一篇发布到公开站点的 Obsidian 笔记。",
) -> str:
    cleaned = text.strip()
    if not cleaned:
        return fallback
    if title:
        normalized_title = title.strip()
        if cleaned.startswith(normalized_title):
            cleaned = cleaned[len(normalized_title) :].lstrip("：: -")
        if not cleaned:
            cleaned = normalized_title
    return cleaned[:120] + ("..." if len(cleaned) > 120 else "")


def build_home_page(tree: FolderNode, notes: list[Note], readme_note: Note | None) -> str:
    current_output = folder_index_output(Path("."))
    latest = sorted(notes, key=lambda note: note.mtime, reverse=True)[:8]

    folder_items = []
    for folder in sorted(tree.children.values(), key=lambda item: item.name.lower()):
        folder_items.append(
            f'<li><a href="{relative_href(current_output, folder_index_output(folder.rel_path))}">{html.escape(folder.name)}</a><div class="entry-meta">{folder.note_count} published note{"s" if folder.note_count != 1 else ""}</div></li>'
        )

    latest_items = []
    for note in latest:
        latest_items.append(
            f'<li><a href="{relative_href(current_output, note.output_path)}">{html.escape(note.title)}</a><div class="entry-meta">{html.escape(note.rel_path.as_posix())}</div><div class="entry-summary">{html.escape(build_summary(note.plain_text, title=note.title))}</div></li>'
        )

    intro_html = ""
    if readme_note is not None:
        intro_html = f'<div class="doc-body">{readme_note.html_body}</div>'
    else:
        intro_html = f'<p class="intro-tagline">{html.escape(SITE_DESCRIPTION)}</p>'

    content = f"""
    <h1 class="page-header">{html.escape(SITE_NAME)}</h1>
    {intro_html}
    <h2>Folders</h2>
    {('<ul class="entry-list">' + ''.join(folder_items) + '</ul>') if folder_items else '<p>No folders have been published yet.</p>'}
    <h2>Recent notes</h2>
    {('<ul class="entry-list">' + ''.join(latest_items) + '</ul>') if latest_items else '<p>No published notes yet.</p>'}
    """
    return page_shell(
        title="首页",
        current_output=current_output,
        nav_html=nav_html(current_output, tree, active_home=True),
        aside_html="",
        content_html=content,
        mobile_title=SITE_NAME,
        is_home=True,
    )


def build_folder_page(folder: FolderNode, tree: FolderNode) -> str:
    current_output = folder_index_output(folder.rel_path)
    breadcrumbs = breadcrumb_html(current_output, folder.rel_path.parent if folder.rel_path != Path(".") else Path("."))
    summary = f"{folder.note_count} published note{'s' if folder.note_count != 1 else ''} in this section."

    child_folder_items = []
    for child in sorted(folder.children.values(), key=lambda item: item.name.lower()):
        child_folder_items.append(
            f'<li><a href="{relative_href(current_output, folder_index_output(child.rel_path))}">{html.escape(child.name)}</a><div class="entry-meta">{child.note_count} note{"s" if child.note_count != 1 else ""}</div></li>'
        )

    child_note_items = []
    for note in sort_notes(folder.notes):
        child_note_items.append(
            f'<li><a href="{relative_href(current_output, note.output_path)}">{html.escape(note.title)}</a><div class="entry-meta">{html.escape(note.date_label)}</div><div class="entry-summary">{html.escape(build_summary(note.plain_text, title=note.title))}</div></li>'
        )

    content = f"""
    <div class="breadcrumbs">{breadcrumbs}</div>
    <h1 class="page-header">{html.escape(folder.name)}</h1>
    <p class="article-summary">{html.escape(summary)}</p>
    <h2>Folders</h2>
    {('<ul class="entry-list">' + ''.join(child_folder_items) + '</ul>') if child_folder_items else '<p>This folder has no subfolders.</p>'}
    <h2>Files</h2>
    {('<ul class="entry-list">' + ''.join(child_note_items) + '</ul>') if child_note_items else '<p>This folder has no notes yet.</p>'}
    """
    return page_shell(
        title=folder.name,
        current_output=current_output,
        nav_html=nav_html(current_output, tree, active_folder=folder.rel_path),
        aside_html="",
        content_html=content,
        mobile_title=folder.name,
    )


def walk_folders(node: FolderNode) -> list[FolderNode]:
    folders = [node]
    for child in sorted(node.children.values(), key=lambda item: item.name.lower()):
        folders.extend(walk_folders(child))
    return folders


def main() -> None:
    if not VAULT_ROOT.exists() or not VAULT_ROOT.is_dir():
        raise SystemExit(f"Vault root not found: {VAULT_ROOT}")
    ensure_dist()

    notes: list[Note] = []
    for path in iter_markdown_files():
        raw = path.read_text(encoding="utf-8")
        frontmatter, body = strip_frontmatter(raw)
        if frontmatter.get("publish") is False:
            continue
        rel_path = path.relative_to(VAULT_ROOT)
        note_key = normalize_key(rel_path.as_posix())
        output_rel = rel_path.with_suffix(".html")
        output_path = DIST_ROOT / output_rel
        title = extract_title(rel_path, body, frontmatter)
        plain_text = strip_markdown(raw)
        notes.append(
            Note(
                source_path=path,
                rel_path=rel_path,
                note_key=note_key,
                output_rel_path=output_rel,
                output_path=output_path,
                title=title,
                frontmatter=frontmatter,
                body_markdown=body,
                plain_text=plain_text,
                mtime=path.stat().st_mtime,
                date_label=safe_date_label(path, frontmatter),
            )
        )

    assets = iter_assets()
    asset_lookup = build_asset_lookup(assets)
    note_lookup, alias_lookup = build_alias_lookup(notes)
    renderer = MarkdownRenderer(note_lookup, alias_lookup, asset_lookup)

    for note in notes:
        html_body, headings, links_to, properties_html = renderer.render(note)
        note.html_body = html_body
        note.headings = headings
        note.links_to = links_to
        note.properties_html = properties_html

    for note in notes:
        for target_key in note.links_to:
            target_note = note_lookup.get(target_key)
            if target_note is not None and note.note_key != target_note.note_key:
                target_note.backlinks.append(note)

    tree = build_tree(notes)
    copy_assets(assets)

    search_index = [
        {
            "title": note.title,
            "path": note.rel_path.as_posix(),
            "excerpt": build_summary(note.plain_text, title=note.title),
            "url": note.output_rel_path.as_posix(),
        }
        for note in sorted(notes, key=lambda item: item.title.lower())
    ]
    write_assets(search_index)

    for note in notes:
        note.output_path.parent.mkdir(parents=True, exist_ok=True)
        note.output_path.write_text(build_note_page(note, tree), encoding="utf-8")

    readme_note = next((note for note in notes if note.rel_path == Path("README.md")), None)
    home_path = folder_index_output(Path("."))
    home_path.write_text(build_home_page(tree, notes, readme_note), encoding="utf-8")

    for folder in walk_folders(tree):
        if folder.rel_path == Path("."):
            continue
        output = folder_index_output(folder.rel_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(build_folder_page(folder, tree), encoding="utf-8")

    print(f"Generated {len(notes)} notes into {DIST_ROOT}")


if __name__ == "__main__":
    main()
