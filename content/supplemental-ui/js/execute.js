/* Repository-owned Showroom execute control for role="execute" blocks. */
(function () {
  'use strict';

  function terminalDocument() {
    if (window.parent === window) return null;
    try {
      var parentDocument = window.parent.document;
      var selectors = [
        'iframe[src*="/showroom/terminal"]',
        'iframe[src*="/terminal"]',
        'iframe[src*="/wetty"]',
        'iframe[src*="/tty"]'
      ];
      for (var index = 0; index < selectors.length; index += 1) {
        var frame = parentDocument.querySelector(selectors[index]);
        if (frame && frame.contentWindow) return frame.contentWindow.document;
      }
    } catch (error) {
      return null;
    }
    return null;
  }

  function findTerminalIframe() {
    if (window.parent === window) return null;
    try {
      var frames = window.parent.document.querySelectorAll('iframe');
      for (var index = 0; index < frames.length; index += 1) {
        var source = frames[index].getAttribute('src') || '';
        if (/\/(showroom\/)?(terminal|wetty|tty)(?:[/?#]|$)/.test(source)) {
          return frames[index];
        }
      }
    } catch (error) {
      return null;
    }
    return null;
  }

  function selectTerminalTab() {
    if (window.parent === window) return;
    try {
      var candidates = window.parent.document.querySelectorAll(
        '[role="tab"], .pf-v6-c-tabs__link, .pf-c-tabs__link, button'
      );
      for (var index = 0; index < candidates.length; index += 1) {
        var label = (candidates[index].textContent || '').trim().toLowerCase();
        if (label === 'terminal' || label === 'bastion') {
          candidates[index].click();
          return;
        }
      }
    } catch (error) {
      // A missing tab is reported on the button after the retry window.
    }
  }

  function pasteCommand(frame, command) {
    try {
      var frameWindow = frame.contentWindow;
      if (frameWindow.wetty_socket && typeof frameWindow.wetty_socket.emit === 'function') {
        frameWindow.wetty_socket.emit('input', command + '\r');
        return true;
      }

      var document = terminalDocument();
      if (!document) return false;
      var textarea = document.querySelector('.xterm-helper-textarea');
      if (!textarea) return false;

      textarea.focus();
      try {
        var transfer = new frameWindow.DataTransfer();
        transfer.setData('text/plain', command);
        textarea.dispatchEvent(new frameWindow.ClipboardEvent('paste', {
          clipboardData: transfer,
          bubbles: true,
          cancelable: true
        }));
      } catch (clipboardError) {
        textarea.value = command;
        textarea.dispatchEvent(new frameWindow.InputEvent('input', {
          data: command,
          inputType: 'insertText',
          bubbles: true
        }));
      }
      window.setTimeout(function () {
        ['keydown', 'keypress', 'keyup'].forEach(function (eventName) {
          textarea.dispatchEvent(new frameWindow.KeyboardEvent(eventName, {
            key: 'Enter',
            code: 'Enter',
            keyCode: 13,
            which: 13,
            bubbles: true,
            cancelable: true
          }));
        });
      }, 60);
      return true;
    } catch (error) {
      return false;
    }
  }

  function setButtonState(button, label, state) {
    button.textContent = label;
    button.dataset.state = state;
    button.disabled = state === 'sending';
  }

  function execute(command, button, remainingAttempts) {
    var frame = findTerminalIframe();
    if (frame && pasteCommand(frame, command)) {
      setButtonState(button, 'Executed', 'success');
      window.setTimeout(function () {
        setButtonState(button, 'Execute', 'ready');
      }, 1800);
      return;
    }
    if (remainingAttempts > 0) {
      window.setTimeout(function () {
        execute(command, button, remainingAttempts - 1);
      }, 150);
      return;
    }
    setButtonState(button, 'Terminal unavailable', 'error');
    window.setTimeout(function () {
      setButtonState(button, 'Execute', 'ready');
    }, 2500);
  }

  function addButton(block) {
    if (block.dataset.executeControl === 'true') return;
    var code = block.querySelector('code');
    var content = block.querySelector('.content');
    if (!code || !content) return;

    var button = document.createElement('button');
    button.type = 'button';
    button.className = 'launchpad-execute-button';
    button.textContent = 'Execute';
    button.title = 'Run this command in the Terminal tab';
    button.setAttribute('aria-label', 'Execute this code in the terminal');
    button.dataset.state = 'ready';
    button.addEventListener('click', function (event) {
      event.preventDefault();
      event.stopPropagation();
      setButtonState(button, 'Sending…', 'sending');
      selectTerminalTab();
      execute(code.textContent.trim(), button, 20);
    });

    content.appendChild(button);
    block.dataset.executeControl = 'true';
  }

  function init() {
    document.querySelectorAll('div.listingblock.execute').forEach(addButton);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
}());
