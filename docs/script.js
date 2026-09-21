/* MoiCedrus. Mejora progresiva; los enlaces de respaldo funcionan sin JavaScript. */
(() => {
  'use strict';
  document.body.classList.add('js');
  const $ = id => document.getElementById(id);
  const themeSelector = $('theme-selector');
  const themeControl = $('theme-control');
  if (themeSelector && themeControl) {
    const themeKey = 'moicedrus-theme';
    const root = document.documentElement;
    const allowedTheme = value => ['light', 'dark'].includes(value) ? value : 'system';
    const systemTheme = typeof window.matchMedia === 'function' ? window.matchMedia('(prefers-color-scheme: dark)') : null;
    const themeMeta = document.querySelector('meta[name="theme-color"]');
    function applyTheme(value) {
      const preference = allowedTheme(value);
      root.dataset.theme = preference;
      themeSelector.value = preference;
      const dark = preference === 'dark' || (preference === 'system' && systemTheme && systemTheme.matches);
      if (themeMeta) themeMeta.setAttribute('content', dark ? '#211e1b' : '#f7f2e7');
    }
    applyTheme(root.dataset.theme);
    themeControl.hidden = false;
    themeSelector.addEventListener('change', () => {
      applyTheme(themeSelector.value);
      try {
        if (root.dataset.theme === 'system') window.localStorage.removeItem(themeKey);
        else window.localStorage.setItem(themeKey, root.dataset.theme);
      } catch { /* El cambio sigue funcionando en esta página. */ }
    });
    const followSystem = () => applyTheme(root.dataset.theme);
    if (systemTheme && typeof systemTheme.addEventListener === 'function') systemTheme.addEventListener('change', followSystem);
    else if (systemTheme && typeof systemTheme.addListener === 'function') systemTheme.addListener(followSystem);
    window.addEventListener('storage', event => {
      if (event.key === themeKey || event.key === null) applyTheme(event.newValue);
    });
  }
  const menuButton = $('menu-toggle');
  const menu = $('page-nav');
  if (menuButton && menu) {
    menuButton.addEventListener('click', () => {
      const open = menuButton.getAttribute('aria-expanded') !== 'true';
      menuButton.setAttribute('aria-expanded', String(open));
      menu.classList.toggle('is-open', open);
      menuButton.textContent = open ? 'Cerrar menú' : 'Menú';
    });
    menu.addEventListener('click', event => {
      if (event.target.closest('a')) {
        menu.classList.remove('is-open');
        menuButton.setAttribute('aria-expanded', 'false');
        menuButton.textContent = 'Menú';
      }
    });
  }

  let toastTimeout;
  function notify(message) {
    const status = $('copy-status');
    if (!status) return;
    status.textContent = message;
    clearTimeout(toastTimeout);
    toastTimeout = setTimeout(() => { status.textContent = ''; }, 5000);
  }
  document.querySelectorAll('[data-copy]').forEach(button => {
    button.hidden = false;
    button.addEventListener('click', async () => {
      const target = $(button.dataset.copy);
      if (!target) return;
      try {
        if (!navigator.clipboard || !window.isSecureContext) throw new Error('Copiado manual');
        await navigator.clipboard.writeText(target.textContent.trim());
        notify('Texto copiado.');
      } catch {
        const range = document.createRange();
        range.selectNodeContents(target);
        const selection = window.getSelection();
        selection.removeAllRanges();
        selection.addRange(range);
        notify('Texto seleccionado. Usa Ctrl+C o ⌘C para copiarlo.');
      }
    });
  });

  const dialog = $('image-dialog');
  let lastImageLink;
  if (dialog && typeof dialog.showModal === 'function') {
    document.querySelectorAll('[data-lightbox]').forEach(link => {
      link.addEventListener('click', event => {
        if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
        event.preventDefault();
        lastImageLink = link;
        const img = link.querySelector('img');
        $('dialog-image').src = link.href;
        $('dialog-image').alt = img ? img.alt : '';
        $('dialog-title').textContent = link.dataset.title || 'Captura de pantalla';
        $('dialog-caption').textContent = link.dataset.caption || 'Imagen de la presentación de septiembre de 2026.';
        dialog.showModal();
        $('close-image').focus();
      });
    });
    $('close-image').addEventListener('click', () => dialog.close());
    dialog.addEventListener('click', event => {
      const r = dialog.getBoundingClientRect();
      if (event.target === dialog && (event.clientX < r.left || event.clientX > r.right || event.clientY < r.top || event.clientY > r.bottom)) dialog.close();
    });
    dialog.addEventListener('close', () => { if (lastImageLink) lastImageLink.focus(); });
  }

  function revealSourceInstructions() {
    const detail = $('instalar-fuente');
    if (detail && window.location.hash === '#instalar-fuente') detail.open = true;
  }
  window.addEventListener('hashchange', revealSourceInstructions);
  revealSourceInstructions();

  const name = document.body.dataset.repo;
  if (!['DPI', 'DendroLen'].includes(name)) return;
  const repo = `rojasbadillamoi/${name}`;
  const repoUrl = `https://github.com/${repo}`;
  const fallbackVersion = document.body.dataset.fallbackVersion;
  function safeRepoUrl(value, prefix) {
    try {
      const url = new URL(value);
      return url.protocol === 'https:' && url.hostname === 'github.com' &&
        !url.username && !url.password && !url.port &&
        url.pathname.startsWith(`/${repo}/${prefix}`) ? url.href : null;
    } catch { return null; }
  }
  function formatSize(bytes) {
    if (!Number.isFinite(bytes) || bytes < 0) return 'Tamaño no informado';
    if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toLocaleString('es-CL', { maximumFractionDigits: 2 })} GiB`;
    return `${(bytes / 1024 ** 2).toLocaleString('es-CL', { minimumFractionDigits: 1, maximumFractionDigits: 1 })} MiB`;
  }
  // Los archivos ZIP/TAR ambiguos no reciben una plataforma inventada.
  function classify(filename) {
    const file = filename.toLowerCase();
    if (/\.(exe|msi|msix)$/.test(file)) return {title:'Windows',mark:'W',kind:'INSTALADOR',suffix:file.slice(file.lastIndexOf('.')),description:`Instala ${name} siguiendo las indicaciones del paquete publicado.`};
    if (/\.(deb|rpm|appimage)$/.test(file)) return {title:'Linux',mark:'L',kind:'PAQUETE',suffix:/appimage$/.test(file)?'.AppImage':file.slice(file.lastIndexOf('.')),description:'Consulta las notas de esta versión para conocer la distribución y arquitectura compatibles.'};
    if (/\.(dmg|pkg)$/.test(file)) return {title:'macOS',mark:'M',kind:'PAQUETE',suffix:file.slice(file.lastIndexOf('.')),description:'Consulta las notas de esta versión para conocer los requisitos del paquete.'};
    return {title:'Archivo de la versión',mark:'↓',kind:'ARCHIVO ADICIONAL',suffix:'',description:'Consulta las notas de la versión para conocer el contenido y el uso de este archivo.'};
  }
  function element(tag, className, value) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (value !== undefined) node.textContent = value;
    return node;
  }
  function assetCard(asset, version) {
    const info = classify(asset.name);
    const card = element('article', 'download-card');
    const top = element('div', 'card-top');
    const mark = element('span', 'platform-mark', info.mark);
    mark.setAttribute('aria-hidden', 'true');
    top.append(mark, element('span', 'file-kind', info.kind));
    const link = element('a', 'button button-primary download-button', `Descargar${info.suffix ? ` ${info.suffix}` : ' archivo'} ↓`);
    link.href = asset.browser_download_url;
    link.setAttribute('aria-label', `Descargar ${asset.name}`);
    card.append(top, element('h3', '', info.title), element('p', 'asset-name', asset.name), element('p', 'download-description', info.description), element('p', 'asset-meta', `${formatSize(asset.size)} · ${version}`), link);
    return card;
  }
  async function updateRelease() {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 8000);
    try {
      const response = await fetch(`https://api.github.com/repos/${repo}/releases/latest`, {signal:controller.signal, headers:{Accept:'application/vnd.github+json'}, credentials:'omit'});
      if (!response.ok) throw new Error('Release no disponible');
      const release = await response.json();
      const releaseUrl = safeRepoUrl(release.html_url, 'releases/tag/');
      if (!releaseUrl || typeof release.tag_name !== 'string' || !release.tag_name.trim() || !Array.isArray(release.assets) || release.draft || release.prerelease) throw new Error('Datos incompletos');
      const version = release.tag_name;
      const assets = release.assets.filter(asset => asset && typeof asset.name === 'string' && asset.name.trim() && asset.state === 'uploaded' && safeRepoUrl(asset.browser_download_url, 'releases/download/'));
      const cards = assets.map(asset => assetCard(asset, version));
      if (!cards.length) {
        const card = element('article', 'download-card');
        const link = element('a', 'button button-secondary', 'Abrir esta versión en GitHub ↗');
        link.href = releaseUrl;
        card.append(element('h3', '', 'Código fuente disponible'), element('p', 'download-description', 'Esta versión no tiene paquetes de descarga adjuntos. Puedes consultar sus notas y descargar el código fuente.'), link);
        cards.push(card);
      }
      $('release-assets').replaceChildren(...cards);
      $('release-version').textContent = version;
      $('release-link').href = releaseUrl;
      $('source-download').href = `${repoUrl}/archive/refs/tags/${encodeURIComponent(version)}.zip`;
      const published = new Date(release.published_at);
      $('release-status').textContent = `Última versión estable verificada en GitHub${release.published_at && !Number.isNaN(published.getTime()) ? ` · ${new Intl.DateTimeFormat('es-CL', {day:'numeric',month:'long',year:'numeric',timeZone:'UTC'}).format(published)}` : ''}.`;
      const windows = assets.find(asset => classify(asset.name).title === 'Windows');
      $('primary-download').href = windows ? windows.browser_download_url : '#descargas';
      $('primary-download-label').textContent = windows ? 'Descargar para Windows' : 'Ver descargas';
      $('hero-release').textContent = windows ? `${version} · ${formatSize(windows.size)} · Instalador Windows` : `${version} · Consulta los archivos disponibles`;
      // La referencia bibliográfica corresponde a su versión y no se cambia automáticamente.
    } catch {
      $('release-status').replaceChildren(document.createTextNode(`No se pudo comprobar la versión más reciente. Se muestran enlaces de respaldo de ${fallbackVersion}. `));
      const link = element('a', '', 'Ver todas las versiones');
      link.href = `${repoUrl}/releases`;
      $('release-status').append(link);
      $('hero-release').textContent = `${fallbackVersion} · Enlace de respaldo · Instalador Windows`;
    } finally { clearTimeout(timeout); }
  }
  updateRelease();
})();
