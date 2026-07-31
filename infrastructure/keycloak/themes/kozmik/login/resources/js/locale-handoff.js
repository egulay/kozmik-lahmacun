(() => {
  const persistLoginLocale = () => {
    const languageTag = document.body?.dataset.loginLocale?.toLowerCase();
    if (!languageTag) return;
    const locale = languageTag.startsWith("tr") ? "tr" : "en";
    document.cookie = `kozmik-login-locale=${locale}; Path=/; SameSite=Lax`;
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", persistLoginLocale, { once: true });
  } else {
    persistLoginLocale();
  }
})();
