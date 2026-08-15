(() => {
    const tg = window.Telegram?.WebApp;
    const BRAND = { header: "#6d28d9", bg: "#07070d" };

    let initData = "";
    let tgUser = null;
    let state = null;
    let currentTab = "home";
    let checkoutPlan = null;
    let checkoutPromo = null;
    let checkoutPaymentMethod = "balance";
    let pendingOrderId = null;
    let pendingOrderType = "deposit";

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
        chip.textContent = state.user.username ? `@${state.user.username}` : name;
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

    function openPaymentUrl(url) {
        if (url && tg?.openLink) {
            tg.openLink(url);
        } else if (url) {
            window.open(url, "_blank");
        }
    }

    function renderHome() {
        const sub = state.subscription;
        const st = subStatus(sub);
        const canTrial = !state.user.trial_used && !sub;

        let html = `<div class="screen-inner">`;

        if (sub?.suspended_device_limit) {
            html += `<div class="alert alert-warning">
                ⚠️ Превышен лимит устройств (${sub.hwid_count}/${sub.max_devices}).
                Удалите лишние и восстановите подписку.
            </div>`;
        }

        html += `<div class="card card-highlight">
            <div class="card-title"><span class="hint-icon">🛡</span> Подписка</div>
            <div class="status-badge">
                <span class="status-dot ${st.dot}"></span>
                ${st.text}
            </div>`;

        if (sub) {
            html += `
                <div class="row"><span class="label">📅 Действует до</span><span class="value">${sub.expires_at_formatted}</span></div>
                <div class="row"><span class="label">⏳ Осталось</span><span class="value">${sub.duration_remaining}</span></div>
                <div class="row"><span class="label">📱 Устройства</span><span class="value">${sub.device_count} / ${sub.max_devices}</span></div>`;

            if (sub.subscription_url) {
                html += `<div class="btn-group">
                    <button class="btn btn-primary" id="copy-sub-url" type="button">🔗 Скопировать ссылку</button>
                    <button class="btn btn-ghost" id="reset-sub" type="button">🔐 Сбросить ссылку</button>
                </div>`;
            }

            if (sub.can_restore) {
                html += `<div class="btn-group">
                    <button class="btn btn-primary" id="restore-sub" type="button">♻️ Восстановить подписку</button>
                </div>`;
            }
        } else {
            html += `<p style="margin-top:14px;font-size:14px;color:var(--text-muted)">
                Оформите тариф или активируйте бесплатный пробный период
            </p>`;
        }

        html += `</div>`;

        html += `<div class="card">
            <div class="card-title"><span class="hint-icon">💰</span> Баланс</div>
            <div class="balance-hero" style="padding:8px 0">
                <div class="balance-amount" style="font-size:36px">${formatMoney(state.user.balance)}</div>
            </div>
            <div class="btn-group">
                <button class="btn btn-secondary" data-goto="balance" type="button">💳 Пополнить</button>
            </div>
        </div>`;

        if (canTrial) {
            html += `<div class="card">
                <div class="card-title"><span class="hint-icon">🎁</span> Пробный период</div>
                <p style="font-size:14px;color:var(--text-muted);margin-bottom:12px">
                    ${state.settings.trial_days} дней бесплатно — один раз для каждого пользователя
                </p>
                <button class="btn btn-primary" id="activate-trial" type="button">Активировать</button>
            </div>`;
        }

        html += `<div class="card">
            <div class="card-title"><span class="hint-icon">⚡</span> Быстрые действия</div>
            <div class="btn-group">
                <button class="btn btn-secondary" data-goto="plans" type="button">💎 Тарифы</button>
                <button class="btn btn-secondary" data-goto="devices" type="button">📱 Устройства</button>
            </div>
        </div></div>`;

        return html;
    }

    function renderPlans() {
        if (!state.plans.length) {
            return `<div class="empty-state"><div class="empty-icon">💎</div><p>Тарифы пока не настроены</p></div>`;
        }

        let html = `<div class="screen-inner"><div class="card"><div class="card-title"><span class="hint-icon">✨</span> Выберите тариф</div>`;
        for (const plan of state.plans) {
            html += `<div class="plan-card" data-plan-id="${plan.id}">
                <div>
                    <div class="plan-name">${esc(plan.name)}</div>
                    <div class="plan-meta">${plan.days} дней${plan.description ? " · " + esc(plan.description) : ""}</div>
                </div>
                <div class="plan-price">${formatMoney(plan.price)}</div>
            </div>`;
        }
        html += `</div></div>`;
        return html;
    }

    function renderDevices() {
        if (!state.subscription) {
            return `<div class="empty-state"><div class="empty-icon">📱</div><p>Нет активной подписки</p>
                <button class="btn btn-primary" style="margin-top:16px" data-goto="plans" type="button">Оформить подписку</button></div>`;
        }

        const sub = state.subscription;
        const canAdd = false; // устройства добавляются автоматически при подключении

        let html = `<div class="screen-inner"><div class="card">
            <div class="card-title"><span class="hint-icon">📱</span> Устройства (${state.devices.length} / ${sub.max_devices})</div>`;

        if (sub.suspended_device_limit) {
            html += `<div class="alert alert-warning">Подключений: ${sub.hwid_count}</div>`;
        }

        if (!state.devices.length) {
            html += `<p style="color:var(--text-muted);font-size:14px">Устройство появится автоматически после добавления подписки в VPN-клиент</p>`;
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

        if (sub.can_restore) {
            html += `<div class="btn-group"><button class="btn btn-primary" id="restore-sub" type="button">♻️ Восстановить</button></div>`;
        }

        if (sub.subscription_url && !sub.suspended_device_limit) {
            html += `<div class="btn-group"><button class="btn btn-ghost" id="reset-sub" type="button">🔐 Сбросить ссылку подписки</button></div>`;
        }

        html += `</div></div>`;
        return html;
    }

    function renderBalance() {
        const s = state.settings;
        let html = `<div class="screen-inner"><div class="card">
            <div class="balance-hero">
                <div class="balance-label">Ваш баланс</div>
                <div class="balance-amount">${formatMoney(state.user.balance)}</div>
            </div>`;

        if (s.yookassa_enabled) {
            html += `<div class="card-title" style="margin-top:8px"><span class="hint-icon">💳</span> Пополнение</div>
                <div class="deposit-custom">
                    <input class="input" id="deposit-amount" type="number" min="${s.deposit_min_amount}" max="${s.deposit_max_amount}" placeholder="Сумма в ₽" inputmode="decimal">
                    <button class="btn btn-primary btn-sm" id="deposit-custom-btn" type="button" style="width:auto;min-width:100px">Оплатить</button>
                </div>
                <p style="font-size:12px;color:var(--text-dim);margin-bottom:10px">от ${s.deposit_min_amount} до ${s.deposit_max_amount.toLocaleString("ru-RU")} ₽</p>
                <div class="amount-grid">`;
            for (const amount of s.deposit_amounts) {
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

        html += `<div class="card"><div class="card-title"><span class="hint-icon">📜</span> История</div>`;
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
        html += `</div></div>`;
        return html;
    }

    function renderProfile() {
        const ref = state.referral;
        const displayName = state.user.first_name
            ? `${state.user.first_name}${state.user.last_name ? " " + state.user.last_name : ""}`
            : (state.user.username ? `@${state.user.username}` : "Telegram");

        let html = `<div class="screen-inner"><div class="card">
            <div class="card-title"><span class="hint-icon">👤</span> Аккаунт</div>
            <div class="row"><span class="label">Имя</span><span class="value">${esc(displayName)}</span></div>
            ${state.user.username ? `<div class="row"><span class="label">Username</span><span class="value">@${esc(state.user.username)}</span></div>` : ""}
            <div class="row"><span class="label">ID</span><span class="value">${state.user.telegram_id}</span></div>
        </div>`;

        html += `<div class="card">
            <div class="card-title"><span class="hint-icon">🎁</span> Рефералы</div>
            <p style="font-size:13px;color:var(--text-muted);margin-bottom:8px">
                ${ref.bonus_percent}% с каждого пополнения приглашённого
            </p>
            <div class="referral-link">${esc(ref.referral_link)}</div>
            <div class="btn-group">
                <button class="btn btn-primary" id="copy-referral" type="button">🔗 Копировать</button>
                <button class="btn btn-secondary" id="share-referral" type="button">📤 Поделиться</button>
            </div>
            <div class="stat-grid" style="margin-top:14px">
                <div class="stat-box"><div class="stat-value">${ref.referrals_count}</div><div class="stat-label">Приглашено</div></div>
                <div class="stat-box"><div class="stat-value">${formatMoney(ref.total_earned)}</div><div class="stat-label">Заработано</div></div>
            </div>
        </div>`;

        html += `<div class="card">
            <div class="card-title"><span class="hint-icon">❓</span> Помощь</div>
            <div class="help-section">
                <h3>Как подключиться</h3>
                <ol style="padding-left:18px">
                    <li>Оформите подписку или trial</li>
                    <li>Скопируйте ссылку подписки</li>
                    <li>Добавьте в VPN-клиент (Happ, v2rayNG, Hiddify)</li>
                </ol>
                <p style="margin-top:12px">
                    <a href="https://t.me/${esc(state.settings.support_username)}" target="_blank" rel="noopener">
                        💬 Поддержка @${esc(state.settings.support_username)}
                    </a>
                </p>
            </div>
        </div></div>`;

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
        checkoutPaymentMethod = "balance";
    }

    function getCheckoutFinalPrice() {
        if (!checkoutPlan) return 0;
        return checkoutPromo ? Number(checkoutPromo.final_price) : Number(checkoutPlan.price);
    }

    function renderPaymentMethods() {
        const final = getCheckoutFinalPrice();
        const canBalance = Number(state.user.balance) >= final;
        const yookassa = state.settings.yookassa_enabled;

        let html = `<div class="payment-methods">`;

        if (canBalance) {
            html += `<div class="pay-option ${checkoutPaymentMethod === "balance" ? "selected" : ""}" data-pay="balance">
                <div class="pay-option-icon">💰</div>
                <div class="pay-option-body">
                    <div class="pay-option-title">Списать с баланса</div>
                    <div class="pay-option-desc">Доступно ${formatMoney(state.user.balance)}</div>
                </div>
            </div>`;
        }

        if (yookassa) {
            html += `<div class="pay-option ${checkoutPaymentMethod === "yookassa" ? "selected" : ""}" data-pay="yookassa">
                <div class="pay-option-icon">💳</div>
                <div class="pay-option-body">
                    <div class="pay-option-title">Оплата ЮKassa</div>
                    <div class="pay-option-desc">Картой или СБП — ${formatMoney(final)}</div>
                </div>
            </div>`;
        }

        if (!canBalance && !yookassa) {
            html += `<div class="alert alert-danger">Недостаточно средств. Пополните баланс.</div>`;
        }

        html += `</div>`;
        return html;
    }

    function openCheckout(planId) {
        checkoutPlan = state.plans.find((p) => p.id === planId);
        if (!checkoutPlan) return;

        checkoutPromo = null;
        const final = getCheckoutFinalPrice();
        checkoutPaymentMethod = Number(state.user.balance) >= final ? "balance" : "yookassa";

        const html = `
            <div class="modal-title">${esc(checkoutPlan.name)}</div>
            <div class="row"><span class="label">📅 Срок</span><span class="value">${checkoutPlan.days} дней</span></div>
            <div class="input-group">
                <label class="input-label">🎟 Промокод</label>
                <div style="display:flex;gap:8px">
                    <input class="input" id="promo-input" placeholder="Необязательно" autocomplete="off">
                    <button class="btn btn-secondary btn-sm" id="apply-promo" type="button">OK</button>
                </div>
            </div>
            <div class="price-breakdown" id="price-breakdown">${renderPriceBreakdown()}</div>
            <div id="payment-methods-wrap">${renderPaymentMethods()}</div>
            <div class="btn-group">
                <button class="btn btn-primary" id="confirm-purchase" type="button">Оформить подписку</button>
                <button class="btn btn-secondary" id="modal-cancel" type="button">Отмена</button>
            </div>`;
        openModal(html);
    }

    function renderPriceBreakdown() {
        if (!checkoutPlan) return "";
        const original = Number(checkoutPlan.price);
        const final = getCheckoutFinalPrice();
        const discount = checkoutPromo ? Number(checkoutPromo.discount_amount) : 0;

        let html = `<div class="row"><span class="label">Стоимость</span><span class="value">${formatMoney(original)}</span></div>`;
        if (discount > 0) {
            html += `<div class="row"><span class="label">Скидка</span><span class="value" style="color:var(--success)">−${formatMoney(discount)}</span></div>`;
        }
        html += `<div class="row"><span class="label">К оплате</span><span class="value">${formatMoney(final)}</span></div>`;
        return html;
    }

    function refreshCheckoutPricing() {
        $("#price-breakdown").innerHTML = renderPriceBreakdown();
        const final = getCheckoutFinalPrice();
        if (checkoutPaymentMethod === "balance" && Number(state.user.balance) < final) {
            checkoutPaymentMethod = state.settings.yookassa_enabled ? "yookassa" : "balance";
        }
        $("#payment-methods-wrap").innerHTML = renderPaymentMethods();
        bindPaymentMethodEvents();
    }

    function bindPaymentMethodEvents() {
        modal.querySelectorAll("[data-pay]").forEach((el) => {
            el.addEventListener("click", () => {
                checkoutPaymentMethod = el.dataset.pay;
                refreshCheckoutPricing();
                haptic("light");
            });
        });
    }

    async function processDeposit(amount) {
        const order = await api("/miniapp/deposit", {
            method: "POST",
            body: JSON.stringify({ amount }),
        });
        pendingOrderId = order.order_id;
        pendingOrderType = "deposit";
        openPaymentUrl(order.payment_url);
        showToast("💳 Откройте страницу оплаты");
        if (currentTab === "balance") render();
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
                refreshCheckoutPricing();
                showToast(`🎟 −${formatMoney(checkoutPromo.discount_amount)}`);
            } catch (e) {
                showToast(e.message);
            }
        });

        bindPaymentMethodEvents();

        $("#confirm-purchase")?.addEventListener("click", async () => {
            const final = getCheckoutFinalPrice();
            const btn = $("#confirm-purchase");
            btn.disabled = true;

            try {
                if (checkoutPaymentMethod === "yookassa") {
                    const order = await api("/miniapp/purchase", {
                        method: "POST",
                        body: JSON.stringify({
                            plan_id: checkoutPlan.id,
                            promo_code_id: checkoutPromo?.promo_code_id || null,
                            payment_method: "yookassa",
                        }),
                    });
                    if (order.order_id) {
                        pendingOrderId = order.order_id;
                        pendingOrderType = "purchase";
                        openPaymentUrl(order.payment_url);
                        closeModal();
                        showToast("💳 Завершите оплату в ЮKassa");
                        switchTab("home");
                    }
                    return;
                }

                if (Number(state.user.balance) < final) {
                    showToast("Недостаточно средств");
                    closeModal();
                    switchTab("balance");
                    return;
                }

                state = await api("/miniapp/purchase", {
                    method: "POST",
                    body: JSON.stringify({
                        plan_id: checkoutPlan.id,
                        promo_code_id: checkoutPromo?.promo_code_id || null,
                        payment_method: "balance",
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

    async function checkPendingPayment() {
        if (!pendingOrderId) return;
        const result = await api(`/miniapp/payment/${pendingOrderId}`);
        if (result.status === "succeeded") {
            pendingOrderId = null;
            if (pendingOrderType === "purchase" || result.subscription) {
                await loadBootstrap();
                showToast("✅ Подписка оформлена!");
                switchTab("home");
            } else {
                await loadBootstrap();
                showToast(`✅ Баланс: ${formatMoney(result.balance)}`);
                render();
            }
            pendingOrderType = "deposit";
        } else {
            showToast("Оплата ещё не поступила");
        }
    }

    async function resetSubscription() {
        if (!(await confirmAction(
            "Сбросить ссылку подписки?\n\nВсе ранее подключённые устройства потеряют доступ. Новую ссылку нужно будет добавить заново."
        ))) return;

        try {
            state = await api("/miniapp/subscription/reset", { method: "POST" });
            updateUserChip();
            showToast("🔐 Ссылка обновлена");
            render();
        } catch (e) {
            showToast(e.message);
        }
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

        $("#reset-sub")?.addEventListener("click", resetSubscription);

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

        screen.querySelectorAll("[data-delete-device]").forEach((el) => {
            el.addEventListener("click", async () => {
                if (!(await confirmAction("Удалить устройство?"))) return;
                try {
                    state = await api(`/miniapp/devices/${el.dataset.deleteDevice}`, {
                        method: "DELETE",
                    });
                    showToast("🗑 Удалено");
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
                try {
                    await processDeposit(Number(el.dataset.deposit));
                } catch (e) {
                    showToast(e.message);
                }
            });
        });

        $("#deposit-custom-btn")?.addEventListener("click", async () => {
            const raw = $("#deposit-amount")?.value?.trim();
            const amount = Number(raw);
            if (!raw || !amount || amount <= 0) {
                showToast("Введите сумму");
                return;
            }
            try {
                await processDeposit(amount);
            } catch (e) {
                showToast(e.message);
            }
        });

        $("#check-payment")?.addEventListener("click", async () => {
            try {
                await checkPendingPayment();
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
                chip.textContent = tgUser.username ? `@${tgUser.username}` : (tgUser.first_name || "...");
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
