(() => {
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
