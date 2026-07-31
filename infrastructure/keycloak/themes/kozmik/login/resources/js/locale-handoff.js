(() => {
  const languageTag = document.body?.dataset.loginLocale?.toLowerCase();
  const locale = languageTag?.startsWith("tr") ? "tr" : "en";
  document.cookie = `kozmik-login-locale=${locale}; Path=/; SameSite=Lax`;
})();
