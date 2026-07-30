<#import "template.ftl" as layout>
<@layout.registrationLayout
  displayMessage=!messagesPerField.existsError('password','password-confirm');
  section>
  <#if section = "header">
    ${msg("updatePasswordTitle")}
  <#elseif section = "form">
    <form id="kc-passwd-update-form" class="kozmik-form"
          action="${url.loginAction}" method="post">
      <div class="kozmik-field">
        <label for="password-new">${msg("passwordNew")}</label>
        <div class="kozmik-password">
          <input id="password-new" name="password-new" type="password"
                 autofocus autocomplete="new-password"
                 aria-invalid="${messagesPerField.existsError('password','password-confirm')?c}">
          <button type="button" class="kozmik-password-toggle"
                  aria-label="${msg('showPassword')}"
                  aria-controls="password-new" data-password-toggle
                  data-label-show="${msg('showPassword')}"
                  data-label-hide="${msg('hidePassword')}">
            <span aria-hidden="true">◉</span>
          </button>
        </div>
      </div>

      <div class="kozmik-field">
        <label for="password-confirm">${msg("passwordConfirm")}</label>
        <div class="kozmik-password">
          <input id="password-confirm" name="password-confirm" type="password"
                 autocomplete="new-password"
                 aria-invalid="${messagesPerField.existsError('password','password-confirm')?c}">
          <button type="button" class="kozmik-password-toggle"
                  aria-label="${msg('showPassword')}"
                  aria-controls="password-confirm" data-password-toggle
                  data-label-show="${msg('showPassword')}"
                  data-label-hide="${msg('hidePassword')}">
            <span aria-hidden="true">◉</span>
          </button>
        </div>
        <#if messagesPerField.existsError('password','password-confirm')>
          <p class="kozmik-field-error" role="alert">
            ${kcSanitize(messagesPerField.getFirstError('password','password-confirm'))?no_esc}
          </p>
        </#if>
      </div>

      <p class="kozmik-password-policy">${msg("kozmikPasswordHelp")}</p>

      <div class="kozmik-actions">
        <#if isAppInitiatedAction??>
          <button class="kozmik-button" type="submit">${msg("doSubmit")}</button>
          <button class="kozmik-button kozmik-button-secondary"
                  type="submit" name="cancel-aia" value="true">${msg("doCancel")}</button>
        <#else>
          <button class="kozmik-button" type="submit">${msg("doSubmit")}</button>
        </#if>
      </div>
    </form>
    <script type="module" src="${url.resourcesPath}/js/passwordVisibility.js"></script>
  </#if>
</@layout.registrationLayout>
