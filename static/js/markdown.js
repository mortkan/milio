/**
 * Renderizador de Markdown básico y seguro.
 * Escapa todo el HTML antes de aplicar un subconjunto de sintaxis.
 */

import { escapeHtml } from "./util.js";

const TOKEN_START = "\u0000";
const TOKEN_END = "\u0000";

function renderInline(value) {
  const codeTokens = [];
  let text = value.replace(/`([^`\n]+)`/g, (_match, code) => {
    codeTokens.push(`<code>${code}</code>`);
    return `${TOKEN_START}${codeTokens.length - 1}${TOKEN_END}`;
  });

  text = text.replace(
    /\[([^\]\n]+)\]\(([^)\s]+)\)/g,
    (match, label, url) => {
      if (!/^(https?:\/\/|mailto:)/i.test(url)) {
        return label;
      }
      const external = /^https?:\/\//i.test(url);
      const target = external
        ? ' target="_blank" rel="noopener noreferrer"'
        : "";
      return `<a href="${url}"${target}>${label}</a>`;
    },
  );

  text = text
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/__([^_]+)__/g, "<strong>$1</strong>")
    .replace(/~~([^~]+)~~/g, "<del>$1</del>")
    .replace(/(^|[\s(])\*([^*\n]+)\*(?=$|[\s).,!?:;])/g, "$1<em>$2</em>")
    .replace(/(^|[\s(])_([^_\n]+)_(?=$|[\s).,!?:;])/g, "$1<em>$2</em>");

  return text.replace(
    new RegExp(`${TOKEN_START}(\\d+)${TOKEN_END}`, "g"),
    (_match, index) => codeTokens[Number(index)] || "",
  );
}

export function renderMarkdown(value) {
  if (!value) {
    return "";
  }

  const lines = escapeHtml(String(value).replace(/\r\n?/g, "\n")).split("\n");
  const html = [];
  let paragraph = [];
  let listType = null;
  let inCode = false;
  let codeLines = [];

  const flushParagraph = () => {
    if (paragraph.length) {
      html.push(`<p>${paragraph.join("<br>")}</p>`);
      paragraph = [];
    }
  };

  const closeList = () => {
    if (listType) {
      html.push(`</${listType}>`);
      listType = null;
    }
  };

  const openList = (type) => {
    if (listType !== type) {
      closeList();
      html.push(`<${type}>`);
      listType = type;
    }
  };

  for (const line of lines) {
    if (line.trim().startsWith("```")) {
      flushParagraph();
      closeList();
      if (!inCode) {
        inCode = true;
        codeLines = [];
      } else {
        html.push(`<pre><code>${codeLines.join("\n")}</code></pre>`);
        inCode = false;
        codeLines = [];
      }
      continue;
    }

    if (inCode) {
      codeLines.push(line);
      continue;
    }

    if (!line.trim()) {
      flushParagraph();
      closeList();
      continue;
    }

    const heading = line.match(/^(#{1,4})\s+(.+)$/);
    if (heading) {
      flushParagraph();
      closeList();
      const level = heading[1].length;
      html.push(`<h${level}>${renderInline(heading[2])}</h${level}>`);
      continue;
    }

    if (/^(?:---+|\*\*\*+|___+)$/.test(line.trim())) {
      flushParagraph();
      closeList();
      html.push("<hr>");
      continue;
    }

    const quote = line.match(/^&gt;\s?(.*)$/);
    if (quote) {
      flushParagraph();
      closeList();
      html.push(`<blockquote>${renderInline(quote[1])}</blockquote>`);
      continue;
    }

    const unordered = line.match(/^\s*[-*+]\s+(.+)$/);
    if (unordered) {
      flushParagraph();
      openList("ul");
      html.push(`<li>${renderInline(unordered[1])}</li>`);
      continue;
    }

    const ordered = line.match(/^\s*\d+\.\s+(.+)$/);
    if (ordered) {
      flushParagraph();
      openList("ol");
      html.push(`<li>${renderInline(ordered[1])}</li>`);
      continue;
    }

    closeList();
    paragraph.push(renderInline(line));
  }

  if (inCode) {
    html.push(`<pre><code>${codeLines.join("\n")}</code></pre>`);
  }
  flushParagraph();
  closeList();
  return html.join("");
}
