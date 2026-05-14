/**
 * dashboard.js — Marcil
 * JS للـ dashboard فقط
 * يقرأ window.APP.csrfToken المُعرَّف في base_dashboard.html
 */

/* ── Sidebar Toggle ── */
(function () {
  var sidebar = document.getElementById('dash-sidebar');
  var overlay = document.getElementById('dash-overlay');
  var toggle  = document.getElementById('sidebar-toggle');

  if (!sidebar || !overlay || !toggle) return;

  toggle.addEventListener('click', function () {
    sidebar.classList.toggle('open');
    overlay.classList.toggle('active');
  });

  overlay.addEventListener('click', function () {
    sidebar.classList.remove('open');
    overlay.classList.remove('active');
  });
})();

/* ── Notifications: Mark Single as Read ── */
var dashNotifWrap = document.getElementById('dash-notif-wrap');
var dashNotifToggle = document.getElementById('dash-notif-toggle');
var dashNotifMenu = document.getElementById('dash-notif-menu');
var dashNotifBadge = document.getElementById('dash-notif-badge');
var dashNotifCount = document.getElementById('dash-notif-count');

if (dashNotifWrap && dashNotifToggle && dashNotifMenu) {
  var closeDashNotifMenu = function () {
    dashNotifMenu.hidden = true;
    dashNotifToggle.setAttribute('aria-expanded', 'false');
  };

  dashNotifToggle.addEventListener('click', function () {
    var isOpen = !dashNotifMenu.hidden;
    dashNotifMenu.hidden = isOpen;
    dashNotifToggle.setAttribute('aria-expanded', isOpen ? 'false' : 'true');
  });

  document.addEventListener('click', function (event) {
    if (!dashNotifWrap.contains(event.target)) {
      closeDashNotifMenu();
    }
  });

  document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape') {
      closeDashNotifMenu();
    }
  });
}

document.querySelectorAll('[data-mark-read-url]').forEach(function (btn) {
  btn.addEventListener('click', function () {
    var url  = this.dataset.markReadUrl;
    var csrf = window.APP && window.APP.csrfToken;
    var card = this.closest('[data-notif-id]');

    if (!url || !csrf) return;

    fetch(url, {
      method: 'POST',
      headers: {
        'X-CSRFToken': csrf,
        'Content-Type': 'application/json'
      }
    })
    .then(function (r) { return r.json(); })
    .then(function (data) {
      if (data.status === 'ok') {
        if (card) {
          card.classList.remove('notification--unread');
          card.classList.add('notification--read');
          card.classList.remove('is-unread');
        }
        btn.remove();
        updateNotifBadge(-1);
      }
    })
    .catch(function () { /* silent fail */ });
  });
});

/* ── Notifications: Mark All as Read ── */
var markAllBtn = document.getElementById('btn-mark-all');
if (markAllBtn) {
  markAllBtn.addEventListener('click', function () {
    var url  = this.dataset.markAllUrl;
    var csrf = window.APP && window.APP.csrfToken;

    if (!url || !csrf) return;

    fetch(url, {
      method: 'POST',
      headers: { 'X-CSRFToken': csrf }
    })
    .then(function (r) { return r.json(); })
    .then(function (data) {
      if (data.status === 'ok') {
        document.querySelectorAll('[data-mark-read-url]').forEach(function (b) { b.remove(); });
        document.querySelectorAll('.notification--unread').forEach(function (c) {
          c.classList.remove('notification--unread');
          c.classList.add('notification--read');
        });
        markAllBtn.remove();
        updateNotifBadge(0, true);
      }
    })
    .catch(function () { /* silent fail */ });
  });
}

/* ── Helper: Update Notification Badge ── */
function updateNotifBadge(delta, reset) {
  var sideBadge = document.querySelector('.dash-nav-item__badge');
  var current = parseInt((dashNotifWrap && dashNotifWrap.dataset.unreadCount) || '0', 10);
  var next = reset ? 0 : current + delta;
  if (next < 0) next = 0;

  if (dashNotifWrap) {
    dashNotifWrap.dataset.unreadCount = String(next);
  }

  if (dashNotifBadge) {
    dashNotifBadge.textContent = next;
    dashNotifBadge.hidden = next === 0;
  }

  if (dashNotifCount) {
    dashNotifCount.textContent = next + ' جديدة';
    dashNotifCount.hidden = next === 0;
  }

  if (sideBadge) {
    if (next <= 0) {
      sideBadge.remove();
    } else {
      sideBadge.textContent = next;
    }
  }
}
