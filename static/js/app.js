// Découvrir Kinshasa — app shell (thème, installation, notifications).

function dkCurrentTheme() {
  return document.documentElement.getAttribute('data-theme') || 'dark';
}

function dkToggleTheme() {
  var next = dkCurrentTheme() === 'light' ? 'dark' : 'light';
  document.documentElement.setAttribute('data-theme', next);
  try { localStorage.setItem('theme', next); } catch (e) {}
  dkUpdateThemeToggleUI();
}

function dkUpdateThemeToggleUI() {
  var isLight = dkCurrentTheme() === 'light';
  document.querySelectorAll('[data-theme-toggle]').forEach(function (btn) {
    var icon = btn.querySelector('[data-theme-icon]');
    if (icon) icon.className = 'ph-fill ' + (isLight ? 'ph-sun' : 'ph-moon');
    var label = btn.querySelector('[data-theme-label]');
    if (label) label.textContent = isLight ? 'Thème clair' : 'Thème sombre';
  });
}

document.addEventListener('DOMContentLoaded', function () {
  dkUpdateThemeToggleUI();
  document.querySelectorAll('[data-theme-toggle]').forEach(function (btn) {
    btn.addEventListener('click', dkToggleTheme);
  });
});

// ---- Installation (PWA) ----

var dkInstallPrompt = null;

function dkIsStandalone() {
  return window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone === true;
}

if ('serviceWorker' in navigator) {
  window.addEventListener('load', function () {
    navigator.serviceWorker.register('/sw.js').catch(function () {});
  });
}

window.addEventListener('beforeinstallprompt', function (event) {
  event.preventDefault();
  dkInstallPrompt = event;
  var btn = document.getElementById('pwa-install-btn');
  if (btn) btn.style.display = 'flex';
});

window.addEventListener('appinstalled', function () {
  dkInstallPrompt = null;
  var btn = document.getElementById('pwa-install-btn');
  if (btn) btn.style.display = 'none';
});

document.addEventListener('DOMContentLoaded', function () {
  var btn = document.getElementById('pwa-install-btn');
  if (btn) {
    btn.addEventListener('click', function () {
      if (!dkInstallPrompt) return;
      dkInstallPrompt.prompt();
      dkInstallPrompt.userChoice.finally(function () { dkInstallPrompt = null; });
    });
  }

  var isIos = /iphone|ipad|ipod/i.test(window.navigator.userAgent);
  var iosHint = document.getElementById('pwa-ios-hint');
  if (iosHint && isIos && !dkIsStandalone()) {
    iosHint.style.display = 'flex';
  }
});

// ---- Notifications push (nouveaux établissements) ----

function dkGetCookie(name) {
  var match = document.cookie.match('(^|;)\\s*' + name + '\\s*=\\s*([^;]+)');
  return match ? decodeURIComponent(match[2]) : null;
}

function dkUrlBase64ToUint8Array(base64String) {
  var padding = '='.repeat((4 - (base64String.length % 4)) % 4);
  var base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
  var raw = window.atob(base64);
  var output = new Uint8Array(raw.length);
  for (var i = 0; i < raw.length; ++i) output[i] = raw.charCodeAt(i);
  return output;
}

function dkPostJson(url, body) {
  return fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': dkGetCookie('csrftoken') },
    body: JSON.stringify(body),
  });
}

function dkSetPushUI(state) {
  // state: 'off' | 'on' | 'unsupported'
  var stateEl = document.getElementById('push-toggle-state');
  var statusEl = document.getElementById('push-toggle-status');
  if (!stateEl) return;
  if (state === 'unsupported') {
    stateEl.textContent = 'Indisponible';
    if (statusEl) statusEl.textContent = "Votre navigateur ne prend pas en charge les notifications.";
  } else if (state === 'on') {
    stateEl.textContent = 'Désactiver';
    if (statusEl) statusEl.textContent = 'Activées sur cet appareil';
  } else {
    stateEl.textContent = 'Activer';
    if (statusEl) statusEl.textContent = "Notification sur cet appareil quand un nouveau site est ajouté";
  }
}

document.addEventListener('DOMContentLoaded', function () {
  var btn = document.getElementById('push-toggle-btn');
  if (!btn) return;

  var vapidKey = btn.getAttribute('data-vapid-key');
  var supported = 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window;
  if (!supported) {
    dkSetPushUI('unsupported');
    btn.disabled = true;
    return;
  }

  navigator.serviceWorker.ready.then(function (reg) {
    return reg.pushManager.getSubscription();
  }).then(function (sub) {
    dkSetPushUI(sub ? 'on' : 'off');
  }).catch(function () {});

  btn.addEventListener('click', function () {
    navigator.serviceWorker.ready.then(function (reg) {
      return reg.pushManager.getSubscription().then(function (existing) {
        if (existing) {
          return dkPostJson('/notifications/push/desabonner/', { endpoint: existing.endpoint })
            .then(function () { return existing.unsubscribe(); })
            .then(function () { dkSetPushUI('off'); });
        }
        return Notification.requestPermission().then(function (permission) {
          if (permission !== 'granted') return;
          return reg.pushManager.subscribe({
            userVisibleOnly: true,
            applicationServerKey: dkUrlBase64ToUint8Array(vapidKey),
          }).then(function (sub) {
            var json = sub.toJSON();
            return dkPostJson('/notifications/push/abonner/', { endpoint: json.endpoint, keys: json.keys })
              .then(function () { dkSetPushUI('on'); });
          });
        });
      });
    }).catch(function () {});
  });
});
