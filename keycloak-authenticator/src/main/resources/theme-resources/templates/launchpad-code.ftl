<#import "template.ftl" as layout>
<@layout.registrationLayout displayMessage=true; section>
  <#if section = "header">Join your Launchpad lab
  <#elseif section = "form">
    <form id="kc-launchpad-code" action="${url.loginAction}" method="post">
      <input type="hidden" name="order_id" value="${(orderId!'')?html}" />
      <div class="form-group"><label for="email">Email</label><input id="email" name="email" type="email" autocomplete="email" required /></div>
      <div class="form-group"><label for="code">Instructor code</label><input id="code" name="code" autocomplete="one-time-code" required /></div>
      <p>Email ownership is not verified. The instructor code is the sole secret.</p>
      <button type="submit">Join lab</button>
    </form>
  </#if>
</@layout.registrationLayout>
