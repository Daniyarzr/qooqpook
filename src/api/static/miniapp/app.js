(() => {
    const tg = window.Telegram?.WebApp;
    const BRAND = { header: "#0140ff", bg: "#010612" };

    let initData = "";
    let tgUser = null;
    let state = null;
    let currentTab = "home";
    let checkoutPlan = null;
    let checkoutPromo = null;
    let pendingOrderId = null;

    const $ = (sel) => document.querySelector(sel);
    const screen = $("#screen");
    const nav = $("#nav");
    const modal = $("#modal");
    const modalContent = $("#modal-content");
    const toastEl = $("#toast");

    const TX_EMOJI = {
        deposit: "💚",
        withdrawal: "🔴",
        subscription_payment: "💎",
        referral_bonus: "🎁",
        admin_adjustment: "⚙️",
    };

    function apiBase() {
        const configured = window.__QOOQ__?.apiPrefix;
        if (configured) return configured.replace(/\/$/, "");
        return `${window.location.origin}/api`;
    }

    function initTelegram() {
        if (!tg) return null;
        tg.ready();
        tg.expand();
        if (typeof tg.disableVerticalSwipes === "function") {
            tg.disableVerticalSwipes();
        }
        tg.setHeaderColor(BRAND.header);
        tg.setBackgroundColor(BRAND.bg);
        initData = tg.initData || "";
        tgUser = tg.initDataUnsafe?.user || null;
        return tgUser;
    }

    function showToast(msg, duration = 2500) {
        toastEl.textContent = msg;
        toastEl.hidden = false;
        clearTimeout(showToast._t);
        showToast._t = setTimeout(() => {
            toastEl.hidden = true;
        }, duration);
    }

    function haptic(type = "light") {
        tg?.HapticFeedback?.impactOccurred(type);
    }

    async function api(path, options = {}) {
        if (!initData) {
            throw new Error("Нет данных авторизации Telegram");
        }
        const url = `${apiBase()}${path.startsWith("/") ? path : `/${path}`}`;
        const res = await fetch(url, {
            ...options,
            headers: {
                "Content-Type": "application/json",
                "X-Telegram-Init-Data": initData,
                ...(options.headers || {}),
            },
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
            const detail = data.detail;
            const message = Array.isArray(detail)
                ? detail.map((d) => d.msg || d).join(", ")
                : detail || `Ошибка ${res.status}`;
            throw new Error(message);
        }
        return data;
    }

    async function loadBootstrap() {
        state = await api("/miniapp/bootstrap");
        updateUserChip();
        if (state.settings.referral_welcome) {
            showToast(`🎁 Реферальная ссылка! Бонус ${state.referral.bonus_percent}% с пополнений`);
        }
    }

    function updateUserChip() {
        const chip = $("#user-chip");
        if (!chip || !state?.user) return;
        const name = state.user.first_name || state.user.username || "Пользователь";
        chip.textContent = state.user.username ? `👤 @${state.user.username}` : `👤 ${name}`;
        chip.hidden = false;
    }

    function formatMoney(v) {
        return `${Number(v).toLocaleString("ru-RU")} ₽`;
    }

    function formatDate(iso) {
        const d = new Date(iso);
        return d.toLocaleDateString("ru-RU", {
            day: "2-digit",
            month: "2-digit",
            year: "numeric",
            hour: "2-digit",
            minute: "2-digit",
        });
    }

    function subStatus(sub) {
        if (!sub) return { text: "Нет подписки", dot: "" };
        if (sub.suspended_device_limit) return { text: "Приостановлена", dot: "suspended" };
        if (sub.status === "expired" || sub.duration_remaining === "истекла") {
            return { text: "Истекла", dot: "" };
        }
        if (sub.is_trial) return { text: "Пробный период", dot: "trial" };
        if (sub.status === "active" || sub.status === "trial") {
            return { text: "Активна", dot: "active" };
        }
        return { text: sub.status, dot: "" };
    }

    function copyText(text) {
        const done = () => {
            showToast("📋 Скопировано");
            haptic("light");
        };
        if (navigator.clipboard?.writeText) {
            navigator.clipboard.writeText(text).then(done).catch(() => tg?.showAlert?.(text));
        } else {
            tg?.showAlert?.(text);
        }
    }

    function confirmAction(message) {
        return new Promise((resolve) => {
            if (tg?.showConfirm) {
                tg.showConfirm(message, resolve);
            } else {
                resolve(window.confirm(message));
            }
        });
    }

    function renderHome() {
        const sub = state.subscription;
        const st = subStatus(sub);
        const canTrial = !state.user.trial_used && !sub;

        let html = "";

        if (sub?.suspended_device_limit) {
            html += `<div class="alert alert-warning">
                ⚠️ Превышен лимит устройств (${sub.hwid_count}/${sub.max_devices}).
                Удалите лишние устройства и восстановите подписку.
            </div>`;
        }

        html += `<div class="card card-highlight">
            <div class="card-title">Подписка</div>
            <div class="status-badge">
                <span class="status-dot ${st.dot}"></span>
                ${st.text}
            </div>`;

        if (sub) {
            html += `
                <div class="row"><span class="label">Действует до</span><span class="value">${sub.expires_at_formatted}</span></div>
                <div class="row"><span class="label">Осталось</span><span class="value">${sub.duration_remaining}</span></div>
                <div class="row"><span class="label">Устройства</span><span class="value">${sub.device_count} / ${sub.max_devices}</span></div>`;

            if (sub.subscription_url) {
                html += `<div class="btn-group">
                    <button class="btn btn-primary" id="copy-sub-url" type="button">🔗 Скопировать ссылку подписки</button>
                </div>`;
            }

            if (sub.can_restore) {
                html += `<div class="btn-group">
                    <button class="btn btn-primary" id="restore-sub" type="button">♻️ Восстановить подписку</button>
                </div>`;
            }
        } else {
            html += `<p style="margin-top:12px;font-size:14px;color:var(--text-muted)">
                Оформите тариф или активируйте бесплатный пробный период
            </p>`;
        }

        html += `</div>`;

        html += `<div class="card">
            <div class="card-title">Баланс</div>
            <div class="balance-hero" style="padding:8px 0">
                <div class="balance-amount" style="font-size:32px">${formatMoney(state.user.balance)}</div>
            </div>
            <div class="btn-group">
                <button class="btn btn-secondary" data-goto="balance" type="button">💳 Пополнить баланс</button>
            </div>
        </div>`;

        if (canTrial) {
            html += `<div class="card">
                <div class="card-title">🎁 Пробный период</div>
                <p style="font-size:14px;color:var(--text-muted);margin-bottom:12px">
                    ${state.settings.trial_days} дней бесплатно — один раз для каждого пользователя
                </p>
                <button class="btn btn-primary" id="activate-trial" type="button">Активировать trial</button>
            </div>`;
        }

        html += `<div class="card">
            <div class="card-title">Быстрые действия</div>
            <div class="btn-group">
                <button class="btn btn-secondary" data-goto="plans" type="button">💎 Выбрать тариф</button>
                <button class="btn btn-secondary" data-goto="devices" type="button">📱 Мои устройства</button>
            </div>
        </div>`;

        return html;
    }

    function renderPlans() {
        if (!state.plans.length) {
            return `<div class="empty-state"><div class="empty-icon">💎</div><p>Тарифы пока не настроены</p></div>`;
        }

        let html = `<div class="card"><div class="card-title">Выберите тариф</div>`;
        for (const plan of state.plans) {
            html += `<div class="plan-card" data-plan-id="${plan.id}">
                <div>
                    <div class="plan-name">${esc(plan.name)}</div>
                    <div class="plan-meta">${plan.days} дней${plan.description ? " · " + esc(plan.description) : ""}</div>
                </div>
                <div class="plan-price">${formatMoney(plan.price)}</div>
            </div>`;
        }
        html += `</div>`;
        return html;
    }

    function renderDevices() {
        if (!state.subscription) {
            return `<div class="empty-state"><div class="empty-icon">📱</div><p>Нет активной подписки</p>
                <button class="btn btn-primary" style="margin-top:16px" data-goto="plans" type="button">Оформить подписку</button></div>`;
        }

        const sub = state.subscription;
        const canAdd = state.devices.length < sub.max_devices && !sub.suspended_device_limit;

        let html = `<div class="card">
            <div class="card-title">Устройства (${state.devices.length} / ${sub.max_devices})</div>`;

        if (sub.suspended_device_limit) {
            html += `<div class="alert alert-warning">Подключений зафиксировано: ${sub.hwid_count}</div>`;
        }

        if (!state.devices.length) {
            html += `<p style="color:var(--text-muted);font-size:14px">Нет устройств</p>`;
        } else {
            for (const d of state.devices) {
                html += `<div class="device-card">
                    <div>
                        <div class="device-name">${esc(d.name)}</div>
                        <div class="device-meta">📊 ${Number(d.traffic_gb).toFixed(2)} ГБ · ${formatDate(d.created_at)}</div>
                    </div>
                    <button class="btn btn-danger btn-sm" data-delete-device="${d.id}" type="button">🗑</button>
                </div>`;
            }
        }

        if (canAdd) {
            html += `<div class="btn-group"><button class="btn btn-primary" id="add-device" type="button">➕ Добавить устройство</button></div>`;
        }

        if (sub.can_restore) {
            html += `<div class="btn-group"><button class="btn btn-primary" id="restore-sub" type="button">♻️ Восстановить подписку</button></div>`;
        }

        html += `</div>`;
        return html;
    }

    function renderBalance() {
        let html = `<div class="card">
            <div class="balance-hero">
                <div class="balance-label">Ваш баланс</div>
                <div class="balance-amount">${formatMoney(state.user.balance)}</div>
            </div>`;

        if (state.settings.yookassa_enabled) {
            html += `<div class="card-title" style="margin-top:8px">Пополнение</div>
                <div class="amount-grid">`;
            for (const amount of state.settings.deposit_amounts) {
                html += `<button class="amount-btn" data-deposit="${amount}" type="button">${amount} ₽</button>`;
            }
            html += `</div>`;

            if (pendingOrderId) {
                html += `<button class="btn btn-secondary" id="check-payment" type="button">🔄 Проверить оплату</button>`;
            }
        } else {
            html += `<div class="alert alert-info">Пополнение временно недоступно</div>`;
        }

        html += `</div>`;

        html += `<div class="card"><div class="card-title">История операций</div>`;
        if (!state.transactions.length) {
            html += `<p style="color:var(--text-muted);font-size:14px">Пока нет операций</p>`;
        } else {
            for (const tx of state.transactions) {
                const emoji = TX_EMOJI[tx.type] || "📝";
                const positive = Number(tx.amount) > 0;
                html += `<div class="tx-item">
                    <span class="tx-emoji">${emoji}</span>
                    <div class="tx-body">
                        <div class="tx-amount ${positive ? "positive" : "negative"}">${positive ? "+" : ""}${formatMoney(tx.amount)}</div>
                        <div class="tx-desc">${esc(tx.description || tx.type)}</div>
                        <div class="tx-date">${formatDate(tx.created_at)}</div>
                    </div>
                </div>`;
            }
        }
        html += `</div>`;
        return html;
    }

    function renderProfile() {
        const ref = state.referral;
        const displayName = state.user.first_name
            ? `${state.user.first_name}${state.user.last_name ? " " + state.user.last_name : ""}`
            : (state.user.username ? `@${state.user.username}` : "Telegram");

        let html = `<div class="card">
            <div class="card-title">Аккаунт Telegram</div>
            <div class="row"><span class="label">Имя</span><span class="value">${esc(displayName)}</span></div>
            ${state.user.username ? `<div class="row"><span class="label">Username</span><span class="value">@${esc(state.user.username)}</span></div>` : ""}
            <div class="row"><span class="label">ID</span><span class="value">${state.user.telegram_id}</span></div>
        </div>`;

        html += `<div class="card">
            <div class="card-title">🎁 Реферальная программа</div>
            <p style="font-size:13px;color:var(--text-muted);margin-bottom:8px">
                Приглашайте друзей — получайте ${ref.bonus_percent}% с каждого их пополнения
            </p>
            <div class="referral-link">${esc(ref.referral_link)}</div>
            <div class="btn-group">
                <button class="btn btn-primary" id="copy-referral" type="button">🔗 Копировать ссылку</button>
                <button class="btn btn-secondary" id="share-referral" type="button">📤 Поделиться</button>
            </div>
            <div class="stat-grid" style="margin-top:14px">
                <div class="stat-box"><div class="stat-value">${ref.referrals_count}</div><div class="stat-label">Приглашено</div></div>
                <div class="stat-box"><div class="stat-value">${formatMoney(ref.total_earned)}</div><div class="stat-label">Заработано</div></div>
            </div>
        </div>`;

        html += `<div class="card">
            <div class="card-title">❓ Помощь</div>
            <div class="help-section">
                <h3>Как подключиться</h3>
                <ol style="padding-left:18px">
                    <li>Оформите подписку или trial</li>
                    <li>Скопируйте ссылку подписки</li>
                    <li>Добавьте в VPN-клиент (Happ, v2rayNG, Hiddify)</li>
                </ol>
            </div>
            <div class="help-section">
                <h3>Клиенты</h3>
                <ul>
                    <li>📱 Android — v2rayNG, Hiddify, Happ</li>
                    <li>🍎 iOS — Streisand, Hiddify, Happ</li>
                    <li>💻 Windows — Hiddify, v2rayN</li>
                </ul>
            </div>
        </div>`;

        return html;
    }

    function esc(s) {
        const d = document.createElement("div");
        d.textContent = s || "";
        return d.innerHTML;
    }

    function render() {
        const renderers = {
            home: renderHome,
            plans: renderPlans,
            devices: renderDevices,
            balance: renderBalance,
            profile: renderProfile,
        };
        screen.innerHTML = renderers[currentTab]?.() || "";
        bindScreenEvents();
    }

    function switchTab(tab) {
        currentTab = tab;
        document.querySelectorAll(".nav-item").forEach((el) => {
            el.classList.toggle("active", el.dataset.tab === tab);
        });
        render();
        haptic("light");
    }

    function openModal(html) {
        modalContent.innerHTML = html;
        modal.hidden = false;
        bindModalEvents();
    }

    function closeModal() {
        modal.hidden = true;
        checkoutPlan = null;
        checkoutPromo = null;
    }

    function openCheckout(planId) {
        checkoutPlan = state.plans.find((p) => p.id === planId);
        if (!checkoutPlan) return;

        checkoutPromo = null;
        const html = `
            <div class="modal-title">${esc(checkoutPlan.name)}</div>
            <div class="row"><span class="label">Срок</span><span class="value">${checkoutPlan.days} дней</span></div>
            <div class="input-group">
                <label class="input-label">Промокод (необязательно)</label>
                <div style="display:flex;gap:8px">
                    <input class="input" id="promo-input" placeholder="Введите код" autocomplete="off">
                    <button class="btn btn-secondary btn-sm" id="apply-promo" type="button">OK</button>
                </div>
            </div>
            <div class="price-breakdown" id="price-breakdown">
                ${renderPriceBreakdown()}
            </div>
            <div class="btn-group">
                <button class="btn btn-primary" id="confirm-purchase" type="button">💳 Оплатить с баланса</button>
                <button class="btn btn-secondary" id="modal-cancel" type="button">Отмена</button>
            </div>`;
        openModal(html);
    }

    function renderPriceBreakdown() {
        if (!checkoutPlan) return "";
        const original = Number(checkoutPlan.price);
        const final = checkoutPromo ? Number(checkoutPromo.final_price) : original;
        const discount = checkoutPromo ? Number(checkoutPromo.discount_amount) : 0;

        let html = `<div class="row"><span class="label">Стоимость</span><span class="value">${formatMoney(original)}</span></div>`;
        if (discount > 0) {
            html += `<div class="row"><span class="label">Скидка</span><span class="value" style="color:var(--success)">−${formatMoney(discount)}</span></div>`;
        }
        html += `<div class="row"><span class="label">К оплате</span><span class="value">${formatMoney(final)}</span></div>`;
        html += `<div class="row"><span class="label">Ваш баланс</span><span class="value">${formatMoney(state.user.balance)}</span></div>`;
        return html;
    }

    function bindModalEvents() {
        $("#modal-cancel")?.addEventListener("click", closeModal);
        modal.querySelector(".modal-backdrop")?.addEventListener("click", closeModal);

        $("#apply-promo")?.addEventListener("click", async () => {
            const code = $("#promo-input")?.value?.trim();
            if (!code) return showToast("Введите промокод");
            try {
                checkoutPromo = await api("/miniapp/promo/validate", {
                    method: "POST",
                    body: JSON.stringify({ code, plan_id: checkoutPlan.id }),
                });
                $("#price-breakdown").innerHTML = renderPriceBreakdown();
                showToast(`🎟 Скидка −${formatMoney(checkoutPromo.discount_amount)}`);
            } catch (e) {
                showToast(e.message);
            }
        });

        $("#confirm-purchase")?.addEventListener("click", async () => {
            const final = checkoutPromo ? Number(checkoutPromo.final_price) : Number(checkoutPlan.price);
            if (Number(state.user.balance) < final) {
                showToast("Недостаточно средств — пополните баланс");
                closeModal();
                switchTab("balance");
                return;
            }
            const btn = $("#confirm-purchase");
            btn.disabled = true;
            try {
                state = await api("/miniapp/purchase", {
                    method: "POST",
                    body: JSON.stringify({
                        plan_id: checkoutPlan.id,
                        promo_code_id: checkoutPromo?.promo_code_id || null,
                    }),
                });
                updateUserChip();
                closeModal();
                showToast("✅ Подписка оформлена!");
                switchTab("home");
            } catch (e) {
                showToast(e.message);
                btn.disabled = false;
            }
        });
    }

    function bindScreenEvents() {
        screen.querySelectorAll("[data-goto]").forEach((el) => {
            el.addEventListener("click", () => switchTab(el.dataset.goto));
        });

        screen.querySelectorAll(".plan-card").forEach((el) => {
            el.addEventListener("click", () => openCheckout(Number(el.dataset.planId)));
        });

        $("#copy-sub-url")?.addEventListener("click", () => {
            copyText(state.subscription.subscription_url);
        });

        $("#copy-referral")?.addEventListener("click", () => {
            copyText(state.referral.referral_link);
        });

        $("#share-referral")?.addEventListener("click", () => {
            if (tg?.openTelegramLink) {
                tg.openTelegramLink(
                    `https://t.me/share/url?url=${encodeURIComponent(state.referral.referral_link)}&text=${encodeURIComponent("QooQ VPN")}`
                );
            } else {
                copyText(state.referral.referral_link);
            }
        });

        $("#activate-trial")?.addEventListener("click", async () => {
            const btn = $("#activate-trial");
            btn.disabled = true;
            try {
                state = await api("/miniapp/trial", { method: "POST" });
                showToast("🎁 Trial активирован!");
                render();
            } catch (e) {
                showToast(e.message);
                btn.disabled = false;
            }
        });

        $("#add-device")?.addEventListener("click", async () => {
            try {
                state = await api("/miniapp/devices", { method: "POST" });
                showToast("✅ Устройство добавлено");
                render();
            } catch (e) {
                showToast(e.message);
            }
        });

        screen.querySelectorAll("[data-delete-device]").forEach((el) => {
            el.addEventListener("click", async () => {
                if (!(await confirmAction("Удалить устройство?"))) return;
                try {
                    state = await api(`/miniapp/devices/${el.dataset.deleteDevice}`, {
                        method: "DELETE",
                    });
                    showToast("🗑 Устройство удалено");
                    render();
                } catch (e) {
                    showToast(e.message);
                }
            });
        });

        const restoreHandler = async () => {
            try {
                state = await api("/miniapp/devices/restore", { method: "POST" });
                showToast("✅ Подписка восстановлена");
                render();
            } catch (e) {
                showToast(e.message);
            }
        };
        $("#restore-sub")?.addEventListener("click", restoreHandler);

        screen.querySelectorAll("[data-deposit]").forEach((el) => {
            el.addEventListener("click", async () => {
                const amount = Number(el.dataset.deposit);
                try {
                    const order = await api("/miniapp/deposit", {
                        method: "POST",
                        body: JSON.stringify({ amount }),
                    });
                    pendingOrderId = order.order_id;
                    if (order.payment_url && tg?.openLink) {
                        tg.openLink(order.payment_url);
                    } else if (order.payment_url) {
                        window.open(order.payment_url, "_blank");
                    }
                    showToast("💳 Откройте страницу оплаты");
                    render();
                } catch (e) {
                    showToast(e.message);
                }
            });
        });

        $("#check-payment")?.addEventListener("click", async () => {
            if (!pendingOrderId) return;
            try {
                const result = await api(`/miniapp/deposit/${pendingOrderId}`);
                if (result.status === "succeeded") {
                    pendingOrderId = null;
                    await loadBootstrap();
                    showToast(`✅ Баланс пополнен: ${formatMoney(result.balance)}`);
                    render();
                } else {
                    showToast("Оплата ещё не поступила");
                }
            } catch (e) {
                showToast(e.message);
            }
        });
    }

    function showError(message) {
        nav.hidden = false;
        screen.innerHTML = `<div class="card"><div class="empty-state">
            <div class="empty-icon">⚠️</div>
            <p>${esc(message)}</p>
            <button class="btn btn-primary" style="margin-top:16px" id="retry-btn" type="button">Повторить</button>
        </div></div>`;
        $("#retry-btn")?.addEventListener("click", () => location.reload());
    }

    async function main() {
        tgUser = initTelegram();

        if (!tg) {
            showError("Откройте приложение в Telegram");
            return;
        }

        if (!initData) {
            showError("Не удалось получить данные Telegram. Закройте и откройте приложение снова.");
            return;
        }

        if (tgUser) {
            const chip = $("#user-chip");
            if (chip) {
                chip.textContent = tgUser.username ? `👤 @${tgUser.username}` : `👤 ${tgUser.first_name || "Загрузка..."}`;
                chip.hidden = false;
            }
        }

        nav.hidden = false;

        document.querySelectorAll(".nav-item").forEach((el) => {
            el.addEventListener("click", () => switchTab(el.dataset.tab));
        });

        try {
            await loadBootstrap();
            render();
        } catch (e) {
            showError(e.message);
        }
    }

    main();
})();
