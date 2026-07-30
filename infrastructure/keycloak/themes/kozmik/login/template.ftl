<#macro registrationLayout bodyClass="" displayInfo=false displayMessage=true
    displayRequiredFields=false showIdentity=true browserTitle="">
<!doctype html>
<html lang="${locale.currentLanguageTag!'en'}" dir="${(locale.rtl!false)?then('rtl','ltr')}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="color-scheme" content="light dark">
  <title><#if browserTitle?has_content>${browserTitle}<#else>${msg("loginTitle", (realm.displayName!'Kozmik Lahmacun'))}</#if></title>
  <#if properties.styles?has_content>
    <#list properties.styles?split(' ') as style>
      <link href="${url.resourcesPath}/${style}" rel="stylesheet">
    </#list>
  </#if>
  <#if scripts??>
    <#list scripts as script>
      <script src="${script}" type="text/javascript"></script>
    </#list>
  </#if>
</head>
<body class="kozmik-auth ${bodyClass}"
      data-login-locale="${locale.currentLanguageTag!'en'}">
  <main class="kozmik-auth-shell">
    <section class="kozmik-card" aria-labelledby="kozmik-page-title">
      <header class="kozmik-card-header">
        <#if showIdentity>
          <div class="kozmik-mark" aria-hidden="true">K</div>
          <p class="kozmik-brand">${realm.displayName!'Kozmik Lahmacun'}</p>
        </#if>
        <h1 id="kozmik-page-title"><#nested "header"></h1>
        <#if showIdentity>
          <p class="kozmik-description">${msg("kozmikAuthDescription")}</p>
        </#if>
      </header>

      <#if realm.internationalizationEnabled && locale.supported?size gt 1>
        <nav class="kozmik-languages" aria-label="${msg('languages')}">
          <#list locale.supported as language>
            <a class="<#if language.languageTag == locale.currentLanguageTag>active</#if>"
               href="${language.url}">${language.label}</a>
          </#list>
        </nav>
      </#if>

      <#if displayMessage && message?has_content
          && (message.type != 'warning' || !isAppInitiatedAction??)>
        <div class="kozmik-alert kozmik-alert-${message.type}" role="alert">
          ${kcSanitize(message.summary)?no_esc}
        </div>
      </#if>

      <div class="kozmik-card-content">
        <#nested "form">
        <#if auth?has_content && auth.showTryAnotherWayLink()>
          <form action="${url.loginAction}" method="post">
            <input type="hidden" name="tryAnotherWay" value="on">
            <button class="kozmik-button kozmik-button-secondary" type="submit">
              ${msg("doTryAnotherWay")}
            </button>
          </form>
        </#if>
        <#nested "socialProviders">
      </div>

      <#if displayInfo>
        <footer class="kozmik-card-footer"><#nested "info"></footer>
      </#if>
    </section>
  </main>
</body>
</html>
</#macro>
