<#import "template.ftl" as layout>
<@layout.registrationLayout displayMessage=true; section>
  <#if section = "header">
    <style>
      body, .pf-v5-c-login { font-family: "Red Hat Text", "Red Hat Display", Helvetica, Arial, sans-serif; }
      .pf-v5-c-login { position: relative; display: flex; min-height: 100vh; align-items: center; justify-content: center; overflow: hidden; background: radial-gradient(circle at 16% 18%, rgba(238, 0, 0, .3), transparent 31%), radial-gradient(circle at 84% 22%, rgba(0, 199, 253, .28), transparent 32%), radial-gradient(circle at 52% 105%, rgba(90, 44, 170, .26), transparent 42%), linear-gradient(135deg, #07090d 0%, #101824 48%, #080a0f 100%); }
      .pf-v5-c-login::before { content: ""; position: absolute; inset: 0; pointer-events: none; opacity: .3; background-image: linear-gradient(rgba(255,255,255,.035) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,.035) 1px, transparent 1px); background-size: 44px 44px; mask-image: linear-gradient(to bottom, rgba(0,0,0,.8), transparent 82%); }
      .pf-v5-c-login__container { display: block; width: 1040px !important; max-width: calc(100vw - 32px) !important; padding: 28px 0; }
      #kc-header { display: none; }
      .pf-v5-c-login__main { display: grid; grid-template-columns: minmax(0, 1.35fr) minmax(340px, .75fr); border: 1px solid rgba(255,255,255,.12); border-radius: 16px; box-shadow: 0 18px 48px rgba(0, 0, 0, .34); overflow: hidden; background: rgba(25, 25, 25, .96); }
      .pf-v5-c-login__main-header { display: block; padding: 34px 40px 38px; border-right: 1px solid rgba(255,255,255,.11); background: linear-gradient(145deg, rgba(255,255,255,.025), rgba(0,113,197,.045)); }
      .pf-v5-c-login__main-body { display: flex; flex-direction: column; justify-content: center; padding: 36px 38px; background: #212121; }
      #kc-page-title { width: 100%; margin: 0; text-align: center !important; }
      .launchpad-brand { text-align: center; }
      .launchpad-logos { display: flex; align-items: center; justify-content: center; gap: 26px; min-height: 60px; margin-bottom: 18px; }
      .launchpad-logo { display: block; height: auto; overflow: visible; }
      .launchpad-logo-redhat { width: 74px; }
      .launchpad-logo-intel { width: 112px; }
      .launchpad-divider { width: 1px; height: 42px; background: #6a6e73; opacity: .55; }
      .launchpad-title { width: 100%; color: #f0f0f0; font-family: "Red Hat Display", "Red Hat Text", Helvetica, Arial, sans-serif; font-size: 28px; font-weight: 700; line-height: 1.2; letter-spacing: -.02em; text-align: center; white-space: nowrap; }
      .launchpad-subtitle { width: 100%; color: #c7c7c7; font-size: 15px; font-weight: 400; line-height: 1.5; margin-top: 8px; text-align: center; }
      .launchpad-overview { margin-top: 28px; text-align: left; }
      .launchpad-kicker { margin: 0 0 8px; color: #73bcf7; font-size: 11px; font-weight: 800; letter-spacing: .13em; text-transform: uppercase; }
      .launchpad-overview h2 { margin: 0; color: #fff; font-family: "Red Hat Display", "Red Hat Text", Helvetica, Arial, sans-serif; font-size: 24px; line-height: 1.2; }
      .launchpad-overview-copy { margin: 10px 0 0; color: #c7c7c7; font-size: 14px; line-height: 1.55; }
      .launchpad-overview h3 { margin: 24px 0 10px; color: #fff; font-size: 14px; }
      .launchpad-paths { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 9px; }
      .launchpad-path { min-height: 76px; padding: 12px 13px; border: 1px solid #3c3f42; border-top: 2px solid #0071c5; border-radius: 7px; background: rgba(12,12,12,.42); }
      .launchpad-path:nth-child(1) { border-top-color: #ee0000; }
      .launchpad-path:nth-child(3) { border-top-color: #f0ab00; }
      .launchpad-path:nth-child(4) { border-top-color: #3e8635; }
      .launchpad-level { display: block; color: #8a8d90; font-size: 10px; font-weight: 800; letter-spacing: .1em; text-transform: uppercase; }
      .launchpad-path strong { display: block; margin-top: 4px; color: #fff; font-size: 13px; line-height: 1.3; }
      .launchpad-formats { display: flex; flex-wrap: wrap; gap: 7px; margin-top: 14px; }
      .launchpad-format { padding: 6px 9px; border-radius: 999px; color: #d2d2d2; background: rgba(255,255,255,.075); font-size: 11px; font-weight: 600; }
      .launchpad-availability { margin: 15px 0 0; padding-left: 11px; border-left: 2px solid #73bcf7; color: #a3a3a3; font-size: 12px; line-height: 1.5; }
      .launchpad-access-title { margin: 0 0 6px; color: #fff; font-family: "Red Hat Display", "Red Hat Text", Helvetica, Arial, sans-serif; font-size: 22px; font-weight: 700; }
      .launchpad-access-copy { margin: 0 0 20px; color: #a3a3a3; font-size: 13px; line-height: 1.5; }
      .launchpad-form { display: grid; gap: 16px; margin-top: 6px; }
      .launchpad-field { display: grid; gap: 8px; }
      .launchpad-label { color: #f0f0f0; font-size: 14px; font-weight: 600; line-height: 1.4; }
      .launchpad-input { box-sizing: border-box; width: 100%; min-height: 46px; padding: 10px 13px; color: #f5f5f5; background: #151515; border: 1px solid #8a8d90; border-radius: 6px; font-size: 16px; }
      .launchpad-input:focus { border-color: #73bcf7; box-shadow: 0 0 0 1px #73bcf7; outline: none; }
      .launchpad-help { color: #a3a3a3; font-size: 13px; line-height: 1.5; margin: -2px 0 0; }
      .launchpad-submit { width: 100%; min-height: 48px; color: #fff; background: #ee0000; border: 1px solid #ee0000; border-radius: 6px; font-size: 16px; font-weight: 600; cursor: pointer; }
      .launchpad-submit:hover { background: #cc0000; border-color: #cc0000; }
      .launchpad-security { margin: 18px 0 0; padding-top: 16px; border-top: 1px solid #3c3f42; color: #8a8d90; font-size: 11px; line-height: 1.5; }
      @media (max-width: 850px) {
        .pf-v5-c-login { align-items: flex-start; overflow: auto; }
        .pf-v5-c-login__container { width: 600px !important; }
        .pf-v5-c-login__main { display: block; }
        .pf-v5-c-login__main-header { border-right: 0; border-bottom: 1px solid rgba(255,255,255,.11); }
      }
      @media (max-width: 600px) {
        .pf-v5-c-login__container { padding: 16px 0; }
        .pf-v5-c-login__main-header { padding: 28px 24px 14px; }
        .pf-v5-c-login__main-body { padding: 28px 24px; }
        .launchpad-logos { gap: 20px; }
        .launchpad-title { font-size: 24px; white-space: normal; }
        .launchpad-paths { grid-template-columns: 1fr; }
      }
    </style>
    <div class="launchpad-brand">
      <div class="launchpad-logos">
        <svg class="launchpad-logo launchpad-logo-redhat" role="img" aria-label="Red Hat" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 192.3 146">
          <path d="M127.47 83.49c12.51 0 30.61-2.58 30.61-17.46a14 14 0 0 0-.31-3.42l-7.45-32.36c-1.72-7.12-3.23-10.35-15.73-16.6C124.89 8.69 103.76.5 97.51.5 91.69.5 90 8 83.06 8c-6.68 0-11.64-5.6-17.89-5.6-6 0-9.91 4.09-12.93 12.5 0 0-8.41 23.72-9.49 27.16A6.43 6.43 0 0 0 42.53 44c0 9.22 36.3 39.45 84.94 39.45M160 72.07c1.73 8.19 1.73 9.05 1.73 10.13 0 14-15.74 21.77-36.43 21.77C78.54 104 37.58 76.6 37.58 58.49a18.45 18.45 0 0 1 1.51-7.33C22.27 52 .5 55 .5 74.22c0 31.48 74.59 70.28 133.65 70.28 45.28 0 56.7-20.48 56.7-36.65 0-12.72-11-27.16-30.83-35.78" fill="#ee0000"/>
          <path d="M160 72.07c1.73 8.19 1.73 9.05 1.73 10.13 0 14-15.74 21.77-36.43 21.77C78.54 104 37.58 76.6 37.58 58.49a18.45 18.45 0 0 1 1.51-7.33l3.66-9.06A6.43 6.43 0 0 0 42.53 44c0 9.22 36.3 39.45 84.94 39.45 12.51 0 30.61-2.58 30.61-17.46a14 14 0 0 0-.31-3.42" fill="#000000"/>
        </svg>
        <span aria-hidden="true" class="launchpad-divider"></span>
        <svg class="launchpad-logo launchpad-logo-intel" role="img" aria-label="Intel" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 388.2 150.6">
          <rect y="2.1" fill="#04c7fd" width="28.1" height="28.1"/>
          <path fill="#04c7fd" d="M27.4 148.5V47.3H.8v101.2h26.6zm176.8 1v-24.8c-3.9 0-7.2-.2-9.6-.6-2.8-.4-4.9-1.4-6.3-2.8-1.4-1.4-2.3-3.4-2.8-6-.4-2.5-.6-5.8-.6-9.8V70.1h19.3V47.3h-19.3V7.8h-26.7v97.9c0 8.3.7 15.3 2.1 20.9 1.4 5.5 3.8 10 7.1 13.4s7.7 5.8 13 7.3c5.4 1.5 12.2 2.2 20.3 2.2h3.5zM357 148.5V0h-26.7v148.5H357zM132.5 57.2c-7.4-8-17.8-12-31-12-6.4 0-12.2 1.3-17.5 3.9-5.2 2.6-9.7 6.2-13.2 10.8l-1.5 1.9V47.3H43v101.2h26.5V96.5c.3-9.5 2.6-16.5 7-21 4.7-4.8 10.4-7.2 16.9-7.2 7.7 0 13.6 2.4 17.5 7 3.8 4.6 5.8 11.1 5.8 19.4v53.7h26.9V91c.1-14.4-3.7-25.8-11.1-33.8zm184 40.5c0-7.3-1.3-14.1-3.8-20.5-2.6-6.3-6.2-11.9-10.7-16.7-4.6-4.8-10.1-8.5-16.5-11.2s-13.5-4-21.2-4c-7.3 0-14.2 1.4-20.6 4.1-6.4 2.8-12 6.5-16.7 11.2s-8.5 10.3-11.2 16.7c-2.8 6.4-4.1 13.3-4.1 20.6 0 7.3 1.3 14.2 3.9 20.6 2.6 6.4 6.3 12 10.9 16.7 4.6 4.7 10.3 8.5 16.9 11.2 6.6 2.8 13.9 4.2 21.7 4.2 22.6 0 36.6-10.3 45-19.9l-19.2-14.6c-4 4.8-13.6 11.3-25.6 11.3-7.5 0-13.7-1.7-18.4-5.2-4.7-3.4-7.9-8.2-9.6-14.1l-.3-.9h79.5v-9.5zm-79.3-9.3c0-7.4 8.5-20.3 26.8-20.4 18.3 0 26.9 12.9 26.9 20.3l-53.7.1z"/>
        </svg>
      </div>
      <div class="launchpad-title">Intel × Red Hat AI Launchpad</div>
      <div class="launchpad-subtitle">Secure access to hands-on AI labs and demos</div>
      <div class="launchpad-overview">
        <p class="launchpad-kicker">Explore · build · engineer · operate</p>
        <h2>Hands-on AI environments for learning, building, and operating</h2>
        <p class="launchpad-overview-copy">Launchpad provides isolated OpenShift environments, visual lab guides, working AI applications, and evidence-backed exercises built around Red Hat software and Intel hardware.</p>
        <h3>What you can do in Launchpad</h3>
        <div class="launchpad-paths">
          <div class="launchpad-path"><span class="launchpad-level">101 · Learn</span><strong>Serve AI models</strong></div>
          <div class="launchpad-path"><span class="launchpad-level">201 · Build</span><strong>Build AI solutions</strong></div>
          <div class="launchpad-path"><span class="launchpad-level">301 · Engineer</span><strong>Engineer agentic systems</strong></div>
          <div class="launchpad-path"><span class="launchpad-level">401 · Operate</span><strong>Operate with evidence</strong></div>
        </div>
        <div class="launchpad-formats" aria-label="Experience formats">
          <span class="launchpad-format">Quick starts</span>
          <span class="launchpad-format">Guided labs</span>
          <span class="launchpad-format">Multi-seat workshops</span>
          <span class="launchpad-format">Live demos</span>
        </div>
        <p class="launchpad-availability">Experiences available to you depend on your event and instructor code. A code grants access only to its assigned lab and seat.</p>
      </div>
    </div>
  <#elseif section = "form">
    <div class="launchpad-access-title">Access your lab</div>
    <p class="launchpad-access-copy">Enter the details supplied by your instructor. Returning participants recover the same active seat.</p>
    <form id="kc-launchpad-code" class="launchpad-form" action="${url.loginAction}" method="post">
      <input type="hidden" name="order_id" value="${orderId!''}" />
      <div class="launchpad-field"><label class="launchpad-label" for="email">Participant email</label><input class="launchpad-input" id="email" name="email" type="email" autocomplete="email" placeholder="participant@example.com" required /></div>
      <div class="launchpad-field"><label class="launchpad-label" for="code">Instructor code</label><input class="launchpad-input" id="code" name="code" autocomplete="one-time-code" placeholder="XXXX-XXXX-XXXX-XXXX-XXXX" required /></div>
      <p class="launchpad-help">Use the email assigned to your seat and the code provided by your instructor. Email ownership is not verified.</p>
      <button class="launchpad-submit" type="submit">Enter lab</button>
    </form>
    <p class="launchpad-security">Your session provides access only to the assigned participant environment. Access expires with the lab order.</p>
  </#if>
</@layout.registrationLayout>
