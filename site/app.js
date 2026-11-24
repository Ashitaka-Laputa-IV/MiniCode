(() => {
  "use strict";

  const STORAGE_KEY = "minicode.site.lang";
  const html = document.documentElement;
  const buttons = Array.from(document.querySelectorAll("[data-lang-button]"));
  const copyButtons = Array.from(
    document.querySelectorAll("[data-copy-target]"),
  );
  const live = document.getElementById("copy-status");

  const normalize = (value) =>
    value && value.toLowerCase().startsWith("en") ? "en" : "zh";
  const current = () => (html.dataset.lang === "en" ? "en" : "zh");

  function labelTables() {
    const lang = current();
    for (const table of document.querySelectorAll("table.responsive-table")) {
      const headers = Array.from(table.querySelectorAll("thead th")).map(
        (th) => {
          const localized = th.querySelector(`.lang-${lang}`);
          return (localized ? localized.textContent : th.textContent).trim();
        },
      );
      for (const row of table.querySelectorAll("tbody tr")) {
        Array.from(row.children).forEach((cell, index) => {
          if (index > 0 && headers[index]) {
            cell.dataset.label = headers[index];
          }
        });
      }
    }
  }

  function initialLang() {
    const params = new URLSearchParams(window.location.search);
    const query = params.get("lang");
    if (query) return normalize(query);
    try {
      const stored = window.localStorage.getItem(STORAGE_KEY);
      if (stored) return normalize(stored);
    } catch (_) {
      /* localStorage can be unavailable in private modes */
    }
    return "zh";
  }

  function setLang(lang, options = {}) {
    const { persist = true, updateUrl = true } = options;
    html.dataset.lang = lang;
    html.lang = lang === "zh" ? "zh-CN" : "en";
    labelTables();
    for (const button of buttons) {
      button.setAttribute(
        "aria-pressed",
        String(button.dataset.langButton === lang),
      );
    }
    if (persist) {
      try {
        window.localStorage.setItem(STORAGE_KEY, lang);
      } catch (_) {
        /* ignore storage failures */
      }
    }
    if (updateUrl) {
      const url = new URL(window.location.href);
      if (lang === "zh") {
        url.searchParams.delete("lang");
      } else {
        url.searchParams.set("lang", lang);
      }
      try {
        window.history.replaceState(null, "", url.toString());
      } catch (_) {
        /* file:// previews can reject history updates */
      }
    }
  }

  for (const button of buttons) {
    button.addEventListener("click", () => {
      setLang(normalize(button.dataset.langButton));
    });
  }

  window.addEventListener("storage", (event) => {
    if (event.key === STORAGE_KEY && event.newValue) {
      setLang(normalize(event.newValue), { persist: false, updateUrl: false });
    }
  });

  setLang(initialLang(), { persist: true, updateUrl: false });

  const labels = {
    zh: { copied: "已复制", failed: "复制失败" },
    en: { copied: "Copied", failed: "Copy failed" },
  };

  async function copyText(text) {
    if (navigator.clipboard && window.isSecureContext) {
      try {
        await navigator.clipboard.writeText(text);
        return true;
      } catch (_) {
        /* fall through to the textarea fallback */
      }
    }
    const area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.select();
    let ok = false;
    try {
      ok = document.execCommand("copy");
    } catch (_) {
      ok = false;
    }
    area.remove();
    return ok;
  }

  for (const button of copyButtons) {
    button.addEventListener("click", async () => {
      const target = document.getElementById(button.dataset.copyTarget);
      if (!target) return;
      const ok = await copyText(target.textContent.trim());
      button.dataset.copied = ok ? "true" : "false";
      if (live) {
        live.textContent = ok
          ? labels[current()].copied
          : labels[current()].failed;
      }
      window.setTimeout(() => {
        button.dataset.copied = "false";
      }, 1600);
    });
  }

  const year = document.getElementById("year");
  if (year) year.textContent = String(new Date().getFullYear());
})();
