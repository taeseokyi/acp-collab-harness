/* VoxLog - 마크다운을 DOM 으로. 전역 VoxMd.render(text) → DocumentFragment. 빌드 없는 바닐라 JS.
   innerHTML 을 쓰지 않는다 - 글은 모두 텍스트 노드로 들어가므로 답에 든 HTML 은 글자 그대로 보인다.
   다루는 것: 제목(#~######), 문단, 글머리·번호 목록(들여쓰기로 겹침), 인용(>), 코드 블록(```), 가로줄, 표,
   글 안의 `코드`·**굵게**·*기울임*·~~취소선~~·[글](http/https 주소). */
(function () {
  'use strict';

  function el(tag, text) {
    var e = document.createElement(tag);
    if (text !== undefined) e.textContent = text;
    return e;
  }

  // 글 안의 꾸밈. 가장 먼저 나오는 표시를 찾아 앞은 글, 안은 다시 푼다.
  var INLINE = [
    { re: /`([^`\n]+)`/, make: function (m) { return el('code', m[1]); } },
    { re: /\[([^\]\n]+)\]\((https?:\/\/[^\s)]+)\)/, make: function (m) {
      var a = el('a');
      a.href = m[2];
      a.target = '_blank';
      a.rel = 'noopener noreferrer';
      inline(a, m[1]);
      return a;
    } },
    { re: /\*\*([^\n]+?)\*\*/, make: function (m) { var b = el('strong'); inline(b, m[1]); return b; } },
    { re: /__([^\n]+?)__/, make: function (m) { var b = el('strong'); inline(b, m[1]); return b; } },
    { re: /~~([^\n]+?)~~/, make: function (m) { var s = el('del'); inline(s, m[1]); return s; } },
    { re: /\*([^*\s][^*\n]*?)\*/, make: function (m) { var i = el('em'); inline(i, m[1]); return i; } }
  ];

  function inline(parent, text) {
    while (text) {
      var best = null, bestRule = null;
      for (var i = 0; i < INLINE.length; i++) {
        var m = INLINE[i].re.exec(text);
        if (m && (!best || m.index < best.index)) { best = m; bestRule = INLINE[i]; }
      }
      if (!best) break;
      if (best.index) parent.appendChild(document.createTextNode(text.slice(0, best.index)));
      parent.appendChild(bestRule.make(best));
      text = text.slice(best.index + best[0].length);
    }
    if (text) parent.appendChild(document.createTextNode(text));
  }

  function inlineLines(parent, lines) {
    lines.forEach(function (ln, i) {
      if (i) parent.appendChild(el('br'));
      inline(parent, ln);
    });
  }

  var RE_HEAD = /^ {0,3}(#{1,6})\s+(.*?)\s*#*\s*$/;
  var RE_FENCE = /^ {0,3}(```|~~~)/;
  var RE_HR = /^ {0,3}([-*_])( *\1){2,} *$/;
  var RE_ITEM = /^(\s*)([-*+]|\d{1,9}[.)])\s+(.*)$/;
  var RE_QUOTE = /^ {0,3}>\s?(.*)$/;
  var RE_TABLE_SEP = /^\s*\|?\s*:?-{1,}:?\s*(\|\s*:?-{1,}:?\s*)*\|?\s*$/;

  function cells(line) {
    var s = line.trim();
    if (s.charAt(0) === '|') s = s.slice(1);
    if (s.charAt(s.length - 1) === '|') s = s.slice(0, -1);
    return s.split('|').map(function (c) { return c.trim(); });
  }

  function isBlockStart(lines, i) {
    var ln = lines[i];
    return RE_HEAD.test(ln) || RE_FENCE.test(ln) || RE_HR.test(ln) || RE_ITEM.test(ln) || RE_QUOTE.test(ln) ||
      (ln.indexOf('|') >= 0 && i + 1 < lines.length && RE_TABLE_SEP.test(lines[i + 1]) && lines[i + 1].indexOf('-') >= 0);
  }

  // 목록: 들여쓰기가 더 깊은 항목은 바로 앞 항목 안의 목록으로.
  function list(lines, i, out) {
    var stack = [];   // {indent, node(ul|ol), li}
    while (i < lines.length) {
      var m = RE_ITEM.exec(lines[i]);
      if (!m) {
        // 항목에 이어지는 들여쓴 줄은 그 항목의 글
        if (stack.length && lines[i].trim() && /^\s+/.test(lines[i]) && !isBlockStart(lines, i)) {
          var li0 = stack[stack.length - 1].li;
          li0.appendChild(document.createTextNode(' '));
          inline(li0, lines[i].trim());
          i++;
          continue;
        }
        break;
      }
      var indent = m[1].replace(/\t/g, '    ').length;
      var ordered = /\d/.test(m[2]);
      while (stack.length && indent < stack[stack.length - 1].indent) stack.pop();
      var top = stack[stack.length - 1];
      if (!top || indent > top.indent) {
        var node = el(ordered ? 'ol' : 'ul');
        if (ordered && parseInt(m[2], 10) !== 1) node.start = parseInt(m[2], 10);
        (top ? top.li : out).appendChild(node);
        top = { indent: indent, node: node, li: null };
        stack.push(top);
      }
      top.li = el('li');
      inline(top.li, m[3]);
      top.node.appendChild(top.li);
      i++;
    }
    return i;
  }

  function blocks(lines, out) {
    var i = 0;
    while (i < lines.length) {
      var ln = lines[i];
      var m;
      if (!ln.trim()) { i++; continue; }
      if ((m = RE_FENCE.exec(ln))) {
        var body = [];
        i++;
        while (i < lines.length && lines[i].trim().indexOf(m[1]) !== 0) { body.push(lines[i]); i++; }
        i++;   // 닫는 줄 (없으면 끝까지가 코드)
        var pre = el('pre');
        pre.appendChild(el('code', body.join('\n')));
        out.appendChild(pre);
        continue;
      }
      if ((m = RE_HEAD.exec(ln))) {
        var h = el('h' + Math.min(6, m[1].length + 2));   // 화면 제목(h1·h2) 아래 단계로
        inline(h, m[2]);
        out.appendChild(h);
        i++;
        continue;
      }
      if (RE_HR.test(ln)) { out.appendChild(el('hr')); i++; continue; }
      if (RE_QUOTE.test(ln)) {
        var q = [];
        while (i < lines.length && (m = RE_QUOTE.exec(lines[i]))) { q.push(m[1]); i++; }
        var bq = el('blockquote');
        blocks(q, bq);
        out.appendChild(bq);
        continue;
      }
      if (RE_ITEM.test(ln)) { i = list(lines, i, out); continue; }
      if (ln.indexOf('|') >= 0 && i + 1 < lines.length && RE_TABLE_SEP.test(lines[i + 1]) && lines[i + 1].indexOf('-') >= 0) {
        var head = cells(ln);
        var table = el('table'), thead = el('thead'), tbody = el('tbody'), tr = el('tr');
        head.forEach(function (c) { var th = el('th'); inline(th, c); tr.appendChild(th); });
        thead.appendChild(tr);
        table.appendChild(thead);
        i += 2;
        while (i < lines.length && lines[i].trim() && lines[i].indexOf('|') >= 0) {
          var row = cells(lines[i]);
          tr = el('tr');
          for (var c = 0; c < head.length; c++) { var td = el('td'); inline(td, row[c] || ''); tr.appendChild(td); }
          tbody.appendChild(tr);
          i++;
        }
        table.appendChild(tbody);
        var wrap = el('div');
        wrap.className = 'md-table';
        wrap.appendChild(table);
        out.appendChild(wrap);
        continue;
      }
      var para = [];
      while (i < lines.length && lines[i].trim() && !(para.length && isBlockStart(lines, i))) { para.push(lines[i].trim()); i++; }
      var p = el('p');
      inlineLines(p, para);
      out.appendChild(p);
    }
  }

  function render(text) {
    var frag = document.createDocumentFragment();
    blocks(String(text == null ? '' : text).replace(/\r\n?/g, '\n').split('\n'), frag);
    return frag;
  }

  window.VoxMd = { render: render };
})();
