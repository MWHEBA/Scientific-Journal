/**
 * public.js — Marcil
 * JS للصفحات العامة فقط
 */

/* ── Navbar Hamburger ── */
document.getElementById('nav-toggle')
  ?.addEventListener('click', function () {
    document.getElementById('mobile-menu').classList.toggle('open');
  });

/* ── Notifications dropdown ── */
const notifWrap = document.getElementById('notif-menu-wrap');
const notifToggle = document.getElementById('notif-menu-toggle');
const notifPanel = document.getElementById('notif-menu-panel');

if (notifWrap && notifToggle && notifPanel) {
  const notifBadge = document.getElementById('notif-badge');
  const notifMenuCount = document.getElementById('notif-menu-count');

  const getCsrfToken = function () {
    const match = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : '';
  };

  const syncUnreadCount = function (nextCount) {
    notifWrap.dataset.unreadCount = String(nextCount);
    if (notifBadge) {
      notifBadge.textContent = String(nextCount);
      notifBadge.hidden = nextCount === 0;
    }
    if (notifMenuCount) {
      notifMenuCount.textContent = nextCount + ' جديدة';
      notifMenuCount.hidden = nextCount === 0;
    }
  };

  const closeNotifMenu = function () {
    notifPanel.hidden = true;
    notifPanel.classList.remove('is-open');
    notifToggle.setAttribute('aria-expanded', 'false');
  };

  notifToggle.addEventListener('click', function () {
    const isOpen = !notifPanel.hidden;
    notifPanel.hidden = isOpen;
    notifPanel.classList.toggle('is-open', !isOpen);
    notifToggle.setAttribute('aria-expanded', isOpen ? 'false' : 'true');
  });

  document.addEventListener('click', function (event) {
    if (!notifWrap.contains(event.target)) {
      closeNotifMenu();
    }
  });

  document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape') {
      closeNotifMenu();
    }
  });

  notifPanel.querySelectorAll('.pub-navbar__notif-mark-read').forEach(function (btn) {
    btn.addEventListener('click', function () {
      const item = btn.closest('[data-notif-item]');
      const markReadUrl = btn.dataset.markReadUrl;
      if (!item || !markReadUrl) {
        return;
      }

      fetch(markReadUrl, {
        method: 'POST',
        headers: {
          'X-CSRFToken': getCsrfToken(),
          'X-Requested-With': 'XMLHttpRequest'
        }
      })
        .then(function (response) {
          if (!response.ok) {
            throw new Error('Request failed');
          }
          item.classList.remove('is-unread');
          btn.remove();
          const current = Number(notifWrap.dataset.unreadCount || '0');
          syncUnreadCount(Math.max(0, current - 1));
        })
        .catch(function () {
          /* silent fail */
        });
    });
  });
}

/* ── Tabs (article_list) ── */
document.querySelectorAll('.tab-btn').forEach(function (btn) {
  btn.addEventListener('click', function () {
    document.querySelectorAll('.tab-btn').forEach(function (b) {
      b.classList.remove('active');
    });
    this.classList.add('active');
  });
});
