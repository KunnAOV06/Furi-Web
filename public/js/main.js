// ============================================================
// FURI WEB - Main JavaScript
// ============================================================

(function() {
    'use strict';

    // ============================================================
    // SIDEBAR
    // ============================================================
    function initSidebar() {
        const sidebar = document.getElementById('sidebar');
        const overlay = document.getElementById('sidebarOverlay');
        const menuBtn = document.getElementById('menuBtn');

        if (!sidebar || !overlay || !menuBtn) return;

        window.toggleSidebar = function() {
            sidebar.classList.toggle('active');
            overlay.classList.toggle('active');
            document.body.style.overflow = sidebar.classList.contains('active') ? 'hidden' : '';
        };

        window.closeSidebar = function() {
            sidebar.classList.remove('active');
            overlay.classList.remove('active');
            document.body.style.overflow = '';
        };

        overlay.addEventListener('click', window.closeSidebar);
        document.querySelectorAll('.sidebar-menu a').forEach(function(link) {
            link.addEventListener('click', window.closeSidebar);
        });

        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape' && sidebar.classList.contains('active')) {
                window.closeSidebar();
            }
        });
    }

    // ============================================================
    // NAVBAR SCROLL
    // ============================================================
    function initNavbarScroll() {
        const navbar = document.getElementById('navbar');
        if (!navbar) return;

        window.addEventListener('scroll', function() {
            if (window.scrollY > 20) {
                navbar.classList.add('scrolled');
            } else {
                navbar.classList.remove('scrolled');
            }
        }, { passive: true });
    }

    // ============================================================
    // FLASH MESSAGES
    // ============================================================
    function initFlashMessages() {
        const alerts = document.querySelectorAll('.flash-message .alert');
        if (!alerts.length) return;

        setTimeout(function() {
            alerts.forEach(function(el) {
                el.style.opacity = '0';
                el.style.transform = 'translateY(-10px)';
                setTimeout(function() {
                    if (el.parentNode) el.remove();
                }, 400);
            });
        }, 3500);
    }

    // ============================================================
    // WELCOME BANNER
    // ============================================================
    function initWelcomeBanner() {
        const banner = document.getElementById('welcomeBanner');
        if (!banner) return;

        window.closeWelcomeBanner = function() {
            banner.classList.remove('show');
            localStorage.setItem('bannerClosed', 'true');
        };

        if (localStorage.getItem('bannerClosed') === 'true') return;

        fetch('/api/welcome-banner')
            .then(function(res) { return res.json(); })
            .then(function(data) {
                if (data.active && data.content) {
                    const contentEl = document.getElementById('bannerContent');
                    if (contentEl) contentEl.innerHTML = data.content;
                    setTimeout(function() {
                        banner.classList.add('show');
                    }, 500);
                }
            })
            .catch(function() {});
    }

    // ============================================================
    // NOTIFICATION MODAL
    // ============================================================
    function initNotificationModal() {
        const modal = document.getElementById('notificationModal');
        if (!modal) return;

        window.closeNotification = function() {
            modal.style.display = 'none';
        };

        window.closeNotificationFor3Hours = function() {
            localStorage.setItem('notificationClosedUntil', String(Date.now() + 3 * 60 * 60 * 1000));
            modal.style.display = 'none';
        };

        const closedUntil = localStorage.getItem('notificationClosedUntil');
        if (closedUntil && Date.now() < parseInt(closedUntil)) {
            return;
        }
        localStorage.removeItem('notificationClosedUntil');

        setTimeout(function() {
            modal.style.display = 'flex';
        }, 1200);

        modal.addEventListener('click', function(e) {
            if (e.target === this) {
                window.closeNotification();
            }
        });
    }

    // ============================================================
    // FADE UP ANIMATION
    // ============================================================
    function initFadeUp() {
        const elements = document.querySelectorAll('.fade-up');
        if (!elements.length) return;

        if ('IntersectionObserver' in window) {
            const observer = new IntersectionObserver(function(entries) {
                entries.forEach(function(entry) {
                    if (entry.isIntersecting) {
                        entry.target.classList.add('visible');
                        observer.unobserve(entry.target);
                    }
                });
            }, {
                threshold: 0.1,
                rootMargin: '0px 0px -30px 0px'
            });

            elements.forEach(function(el) {
                observer.observe(el);
            });
        } else {
            elements.forEach(function(el) {
                el.classList.add('visible');
            });
        }
    }

    // ============================================================
    // PASSWORD TOGGLE
    // ============================================================
    window.togglePassword = function(inputId, iconId) {
        const input = document.getElementById(inputId);
        const icon = document.getElementById(iconId);
        if (!input || !icon) return;

        if (input.type === 'password') {
            input.type = 'text';
            icon.classList.remove('fa-eye-slash');
            icon.classList.add('fa-eye');
        } else {
            input.type = 'password';
            icon.classList.remove('fa-eye');
            icon.classList.add('fa-eye-slash');
        }
    };

    // ============================================================
    // COPY TO CLIPBOARD
    // ============================================================
    window.copyToClipboard = function(text, label) {
        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(text)
                .then(function() {
                    showToast('✅ Đã sao chép ' + label);
                })
                .catch(function() {
                    fallbackCopy(text, label);
                });
        } else {
            fallbackCopy(text, label);
        }
    };

    function fallbackCopy(text, label) {
        const textarea = document.createElement('textarea');
        textarea.value = text;
        textarea.style.position = 'fixed';
        textarea.style.opacity = '0';
        document.body.appendChild(textarea);
        textarea.select();
        try {
            document.execCommand('copy');
            showToast('✅ Đã sao chép ' + label);
        } catch (e) {
            showToast('❌ Sao chép thất bại');
        }
        document.body.removeChild(textarea);
    }

    // ============================================================
    // TOAST NOTIFICATION
    // ============================================================
    function showToast(message) {
        const toast = document.createElement('div');
        toast.style.cssText = `
            position: fixed;
            bottom: 80px;
            left: 50%;
            transform: translateX(-50%);
            padding: 0.5rem 1rem;
            background: var(--bg-card-glass);
            border: 1px solid rgba(255,255,255,0.05);
            border-radius: var(--radius-sm);
            color: var(--text-primary);
            font-size: 0.7rem;
            font-weight: 500;
            z-index: 9999;
            box-shadow: var(--shadow-premium);
            max-width: 90%;
            animation: slideDown 0.4s cubic-bezier(0.34, 1.56, 0.64, 1);
            backdrop-filter: blur(10px);
            border-left: 3px solid var(--neon-green);
        `;
        toast.textContent = message;
        document.body.appendChild(toast);
        setTimeout(function() {
            toast.style.opacity = '0';
            toast.style.transform = 'translateX(-50%) translateY(-10px)';
            setTimeout(function() {
                if (toast.parentNode) toast.remove();
            }, 300);
        }, 3000);
    }

    // ============================================================
    // FILE UPLOAD - Update filename
    // ============================================================
    window.updateFileName = function(input, labelId) {
        const label = document.getElementById(labelId);
        if (!label) return;

        if (input.files && input.files[0]) {
            const size = (input.files[0].size / 1024 / 1024).toFixed(2);
            label.innerHTML = '<i class="fas fa-check-circle" style="color: var(--neon-green);"></i> Đã chọn: ' + input.files[0].name + ' (' + size + 'MB)';
        } else {
            label.innerHTML = '';
        }
    };

    // ============================================================
    // SET AMOUNT (Deposit)
    // ============================================================
    window.setAmount = function(amount) {
        const input = document.querySelector('input[name="amount"]');
        if (input) {
            input.value = amount;
            input.focus();
        }
    };

    // ============================================================
    // TOGGLE DEMO
    // ============================================================
    window.toggleDemo = function() {
        const checkbox = document.getElementById('has_demo');
        const demoSection = document.getElementById('demo_section');
        if (checkbox && demoSection) {
            demoSection.style.display = checkbox.checked ? 'block' : 'none';
            if (checkbox.checked) window.updateDemoFields();
        }
    };

    window.updateDemoFields = function() {
        const demoType = document.getElementById('demo_type');
        const fileSection = document.getElementById('demo_file_section');
        const linkSection = document.getElementById('demo_link_section');
        
        if (!demoType) return;
        const type = demoType.value;
        
        if (fileSection) {
            fileSection.style.display = (type === 'file' || type === 'both') ? 'block' : 'none';
        }
        if (linkSection) {
            linkSection.style.display = (type === 'link' || type === 'both') ? 'block' : 'none';
        }
    };

    // ============================================================
    // INIT
    // ============================================================
    document.addEventListener('DOMContentLoaded', function() {
        initSidebar();
        initNavbarScroll();
        initFlashMessages();
        initWelcomeBanner();
        initNotificationModal();
        initFadeUp();
    });

})();