<#import "template.ftl" as layout>
<@layout.registrationLayout
  displayMessage=!messagesPerField.existsError('username','password')
  displayInfo=realm.password && realm.registrationAllowed && !registrationDisabled??
  showIdentity=false
  browserTitle=msg("kozmikLoginTitle");
  section>
  <#if section = "header">
    ${msg("kozmikLoginTitle")}
  <#elseif section = "form">
    <#if realm.password>
      <form id="kc-form-login" class="kozmik-form"
            onsubmit="login.disabled = true; return true;"
            action="${url.loginAction}" method="post">
        <#if !usernameHidden??>
          <div class="kozmik-field">
            <label for="username">
              <#if !realm.loginWithEmailAllowed>
                ${msg("username")}
              <#elseif !realm.registrationEmailAsUsername>
                ${msg("usernameOrEmail")}
              <#else>
                ${msg("email")}
              </#if>
            </label>
            <input id="username" name="username" value="${(login.username!'')}"
                   type="text" autofocus autocomplete="username" dir="ltr"
                   aria-invalid="${messagesPerField.existsError('username','password')?c}">
          </div>
        </#if>

        <div class="kozmik-field">
          <div class="kozmik-label-row">
            <label for="password">${msg("password")}</label>
            <#if realm.resetPasswordAllowed>
              <a href="${url.loginResetCredentialsUrl}">${msg("doForgotPassword")}</a>
            </#if>
          </div>
          <div class="kozmik-password">
            <input id="password" name="password" type="password"
                   autocomplete="current-password"
                   aria-invalid="${messagesPerField.existsError('username','password')?c}">
            <button type="button" class="kozmik-password-toggle"
                    aria-label="${msg('showPassword')}"
                    aria-controls="password" data-password-toggle
                    data-label-show="${msg('showPassword')}"
                    data-label-hide="${msg('hidePassword')}">
              <span aria-hidden="true">◉</span>
            </button>
          </div>
          <#if messagesPerField.existsError('username','password')>
            <p class="kozmik-field-error" role="alert">
              ${kcSanitize(messagesPerField.getFirstError('username','password'))?no_esc}
            </p>
          </#if>
        </div>

        <#if realm.rememberMe && !usernameHidden??>
          <label class="kozmik-checkbox">
            <input id="rememberMe" name="rememberMe" type="checkbox"
              <#if login.rememberMe??>checked</#if>>
            <span>${msg("rememberMe")}</span>
          </label>
        </#if>

        <input type="hidden" name="credentialId"
          <#if auth.selectedCredential?has_content>value="${auth.selectedCredential}"</#if>>
        <button id="kc-login" class="kozmik-button" name="login" type="submit">
          ${msg("doLogIn")}
        </button>
      </form>
      <script type="module" src="${url.resourcesPath}/js/passwordVisibility.js"></script>
    </#if>
  <#elseif section = "info">
    <#if realm.password && realm.registrationAllowed && !registrationDisabled??>
      <span>${msg("noAccount")} <a href="${url.registrationUrl}">${msg("doRegister")}</a></span>
    </#if>
  <#elseif section = "socialProviders">
    <#if realm.password && social?? && social.providers?has_content>
      <div class="kozmik-social">
        <div class="kozmik-divider"><span>${msg("identity-provider-login-label")}</span></div>
        <#list social.providers as provider>
          <a class="kozmik-button kozmik-button-secondary"
             id="social-${provider.alias}" href="${provider.loginUrl}">
            ${provider.displayName!}
          </a>
        </#list>
      </div>
    </#if>
  </#if>
</@layout.registrationLayout>
