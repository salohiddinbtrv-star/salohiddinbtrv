const socket = io();
const messagesBox = document.getElementById('messages-box');
const chatList = document.getElementById('chat-list');
const chatHeaderTitle = document.getElementById('chat-header-title');
const anonLimitBadge = document.getElementById('anon-limit-badge');

const STORAGE_KEY = 'notfic_ai_chats';
const ACTIVE_KEY = 'notfic_active_chat';
const THEME_KEY = 'notfic_theme';
const PUBLIC_ID = 'public';
const PUBLIC_STORAGE_KEY = 'notfic_public_history';

const IS_LOGGED_IN = document.body.getAttribute('data-logged-in') === 'true';
const ANON_LIMIT = parseInt(document.body.getAttribute('data-anon-limit') || '10', 10);

let isConnected = false;
const sentMessageIds = new Set();
let lastRenderedKey = null;
let cachedFriendsList = [];
const REACTION_EMOJIS = ['👍', '❤️', '😂', '😮', '😢'];

/* ---------- MOBIL BALANDLIK TUZATISH ---------- */
function setViewportHeight() {
    document.documentElement.style.setProperty('--vh', window.innerHeight * 0.01 + 'px');
}
setViewportHeight();
window.addEventListener('resize', setViewportHeight);

/* ---------- HAMBURGER / MOBIL MENYU ---------- */
function openSidebar() {
    document.getElementById('sidebar').classList.add('open');
    document.getElementById('sidebar-overlay').classList.add('open');
}

function closeSidebar() {
    document.getElementById('sidebar').classList.remove('open');
    document.getElementById('sidebar-overlay').classList.remove('open');
}

/* ---------- ILOVALAR MODAL ---------- */
function openAppsModal() {
    document.getElementById('apps-modal').classList.add('open');
    closeSidebar();
}

function closeAppsModal() {
    document.getElementById('apps-modal').classList.remove('open');
}

/* ---------- AI SUHBATLARINI SAQLASH ---------- */
function loadChats() {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}');
}

function saveChats(chats) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(chats));
}

function getActiveChatId() {
    return localStorage.getItem(ACTIVE_KEY) || PUBLIC_ID;
}

function setActiveChatId(id) {
    localStorage.setItem(ACTIVE_KEY, id);
}

function isPublicActive() {
    return getActiveChatId() === PUBLIC_ID;
}

function newAIChat() {
    const chats = loadChats();
    const id = 'chat_' + Date.now();
    chats[id] = { id: id, title: 'Yangi AI suhbat', messages: [] };
    saveChats(chats);
    setActiveChatId(id);
    renderChatList();
    renderMessages();
    updateHeader();
    closeSidebar();
}

function switchToPublic() {
    setActiveChatId(PUBLIC_ID);
    renderChatList();
    renderMessages();
    updateHeader();
    closeSidebar();
}

function updateHeader() {
    if (isPublicActive()) {
        chatHeaderTitle.textContent = '💬 Ochiq Suhbat';
        document.getElementById('public-chat-item').classList.add('active');
    } else {
        const activeId = getActiveChatId();
        if (activeId.indexOf('friend_') === 0) return;
        const chats = loadChats();
        const chat = chats[activeId];
        chatHeaderTitle.textContent = '🤖 ' + (chat ? chat.title : 'AI suhbat');
        document.getElementById('public-chat-item').classList.remove('active');
    }
}

/* ---------- AI SUHBATLAR RO'YXATI (yigiladigan) ---------- */
const CHAT_LIST_VISIBLE_COUNT = 4;
let chatListExpanded = false;

function makeChatListItem(id, chats, activeId) {
    const chat = chats[id];
    const item = document.createElement('div');
    item.className = 'chat-item chat-item-deletable' + (id === activeId ? ' active' : '');

    const titleSpan = document.createElement('span');
    titleSpan.className = 'chat-item-title';
    titleSpan.textContent = chat.title;
    titleSpan.onclick = (function (chatId) {
        return function () {
            setActiveChatId(chatId);
            renderChatList();
            renderMessages();
            updateHeader();
            closeSidebar();
        };
    })(id);

    const menuWrap = document.createElement('div');
    menuWrap.className = 'chat-item-menu-wrap';

    const menuBtn = document.createElement('button');
    menuBtn.className = 'chat-item-menu-btn';
    menuBtn.setAttribute('aria-label', 'Suhbat menyusi');
    menuBtn.innerHTML = '⋯';
    menuBtn.onclick = function (event) {
        event.stopPropagation();
        document.querySelectorAll('.chat-item-menu-wrap.open').forEach(function (w) {
            if (w !== menuWrap) w.classList.remove('open');
        });
        menuWrap.classList.toggle('open');
    };

    const dropdown = document.createElement('div');
    dropdown.className = 'chat-item-dropdown';

    const deleteOption = document.createElement('button');
    deleteOption.className = 'chat-item-dropdown-option';
    deleteOption.textContent = "O'chirish";
    deleteOption.onclick = (function (chatId) {
        return function (event) {
            event.stopPropagation();
            menuWrap.classList.remove('open');
            deleteAIChat(chatId);
        };
    })(id);

    dropdown.appendChild(deleteOption);
    menuWrap.appendChild(menuBtn);
    menuWrap.appendChild(dropdown);

    item.appendChild(titleSpan);
    item.appendChild(menuWrap);
    return item;
}

document.addEventListener('click', function () {
    document.querySelectorAll('.chat-item-menu-wrap.open').forEach(function (w) {
        w.classList.remove('open');
    });
});

function deleteAIChat(chatId) {
    if (!confirm("Bu AI suhbatini ochirishni tasdiqlaysizmi?")) return;
    const chats = loadChats();
    delete chats[chatId];
    saveChats(chats);

    if (getActiveChatId() === chatId) {
        switchToPublic();
    } else {
        renderChatList();
    }
}

function renderChatList() {
    const chats = loadChats();
    const activeId = getActiveChatId();
    const ids = Object.keys(chats).sort(function(a, b) { return b.localeCompare(a); });

    chatList.innerHTML = '';
    const toggleBtn = document.getElementById('chat-list-toggle-btn');

    if (ids.length === 0) {
        chatList.innerHTML = '<span class="sidebar-empty">Hali AI suhbat yoq</span>';
        if (toggleBtn) toggleBtn.style.display = 'none';
        return;
    }

    const visibleIds = ids.slice(0, CHAT_LIST_VISIBLE_COUNT);
    const extraIds = ids.slice(CHAT_LIST_VISIBLE_COUNT);

    visibleIds.forEach(function (id) {
        chatList.appendChild(makeChatListItem(id, chats, activeId));
    });

    if (extraIds.length > 0) {
        const outer = document.createElement('div');
        outer.className = 'chat-list-extra-outer' + (chatListExpanded ? ' expanded' : '');
        outer.id = 'chat-list-extra-outer';

        const inner = document.createElement('div');
        inner.className = 'chat-list-extra-inner';
        extraIds.forEach(function (id) {
            inner.appendChild(makeChatListItem(id, chats, activeId));
        });
        outer.appendChild(inner);
        chatList.appendChild(outer);

        if (toggleBtn) {
            toggleBtn.style.display = 'inline-flex';
            toggleBtn.classList.toggle('expanded', chatListExpanded);
        }
    } else if (toggleBtn) {
        toggleBtn.style.display = 'none';
        toggleBtn.classList.remove('expanded');
    }
}

function toggleChatListExpand() {
    chatListExpanded = !chatListExpanded;
    const outer = document.getElementById('chat-list-extra-outer');
    const btn = document.getElementById('chat-list-toggle-btn');
    if (outer) outer.classList.toggle('expanded', chatListExpanded);
    if (btn) btn.classList.toggle('expanded', chatListExpanded);
}

/* ---------- OCHIQ SUHBAT TARIXI ---------- */
function loadPublicHistory() {
    return JSON.parse(localStorage.getItem(PUBLIC_STORAGE_KEY) || '[]');
}

function savePublicHistory(list) {
    localStorage.setItem(PUBLIC_STORAGE_KEY, JSON.stringify(list.slice(-100)));
}

/* ---------- EKRANGA CHIQARISH ---------- */
function renderMessages() {
    const activeId = getActiveChatId();
    if (activeId.indexOf('friend_') === 0) return;

    messagesBox.innerHTML = '';
    lastRenderedKey = null;

    if (isPublicActive()) {
        const history = loadPublicHistory();
        if (history.length === 0) {
            messagesBox.innerHTML = '<div class="empty-state"><h2>Ochiq Suhbat</h2><p>Bu yerga yozgan xabaringizni saytdagi hamma korishi mumkin.</p></div>';
            return;
        }
        history.forEach(function (m) { appendMessageToDOM(m, false); });
    } else {
        const chats = loadChats();
        const chat = chats[activeId];
        if (!chat || chat.messages.length === 0) {
            messagesBox.innerHTML = '<div class="empty-state"><h2>Nima bilan yordam beray?</h2><p>Bu suhbat faqat sizga korinadi.</p></div>';
            return;
        }
        chat.messages.forEach(function (m) { appendMessageToDOM(m, false); });
    }

    messagesBox.scrollTop = messagesBox.scrollHeight;
}

function avatarHtmlFor(data) {
    if (data.isAI) {
        return '<div class="msg-avatar msg-avatar-ai">⚡</div>';
    }
    if (data.avatar) {
        return '<img src="' + data.avatar + '" class="msg-avatar" alt="">';
    }
    const initial = data.username ? data.username[0].toUpperCase() : '?';
    return '<div class="msg-avatar msg-avatar-fallback">' + initial + '</div>';
}

function buildFeedbackHtml(data) {
    const p = encodeURIComponent(data.prompt || '');
    const r = encodeURIComponent(data.message || '');
    return '<div class="ai-feedback">' +
        '<button class="feedback-btn" onclick="sendAIFeedback(\'' + p + '\',\'' + r + '\',1,this)" aria-label="Yoqdi">👍</button>' +
        '<button class="feedback-btn" onclick="sendAIFeedback(\'' + p + '\',\'' + r + '\',-1,this)" aria-label="Yoqmadi">👎</button>' +
        '</div>';
}

async function sendAIFeedback(promptEnc, respEnc, rating, btnEl) {
    const wrap = btnEl.parentElement;
    wrap.querySelectorAll('.feedback-btn').forEach(function (b) { b.disabled = true; });
    btnEl.classList.add('feedback-selected');

    try {
        await fetch('/api/ai/feedback', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                prompt: decodeURIComponent(promptEnc),
                response: decodeURIComponent(respEnc),
                rating: rating
            })
        });
    } catch (e) {
        console.error(e);
    }
}

function currentChatKind() {
    const activeId = getActiveChatId();
    if (activeId === PUBLIC_ID) return 'public';
    if (activeId.indexOf('friend_') === 0) return 'friend';
    if (activeId.indexOf('group_') === 0) return 'group';
    return 'ai';
}

function buildReactionHtml(data) {
    const current = data.reaction || '';
    const badge = current
        ? '<span class="msg-reaction-badge" onclick="toggleReactionPicker(this)">' + current + '</span>'
        : '<button class="reaction-add-btn" onclick="toggleReactionPicker(this)">🙂+</button>';
    const options = REACTION_EMOJIS.map(function (e) {
        return '<span class="reaction-option" onclick="pickReaction(this,\'' + e + '\')">' + e + '</span>';
    }).join('');
    return '<div class="msg-reaction-row">' + badge + '<div class="reaction-picker">' + options + '</div></div>';
}

function toggleReactionPicker(el) {
    const row = el.closest('.msg-reaction-row');
    document.querySelectorAll('.msg-reaction-row.open').forEach(function (r) {
        if (r !== row) r.classList.remove('open');
    });
    row.classList.toggle('open');
}

function pickReaction(el, emoji) {
    const msgRow = el.closest('.message-row');
    const reactionRow = el.closest('.msg-reaction-row');
    reactionRow.classList.remove('open');

    const msgId = msgRow.getAttribute('data-msg-id');
    const kind = msgRow.getAttribute('data-chat-kind');
    if (!msgId) return;

    if (kind === 'public') {
        socket.emit('react_public', { msg_id: parseInt(msgId, 10), emoji: emoji });
    } else if (kind === 'friend') {
        const activeId = getActiveChatId();
        const friendId = parseInt(activeId.replace('friend_', ''), 10);
        socket.emit('react_friend', { msg_id: parseInt(msgId, 10), to_user_id: friendId, emoji: emoji });
    }
}

function appendMessageToDOM(data, animate) {
    const rowKind = data.isAI ? 'ai' : (data.isMine ? 'mine' : 'other');
    const groupKey = rowKind + '::' + data.username;
    const isGrouped = (groupKey === lastRenderedKey);
    lastRenderedKey = groupKey;

    const rowClass = data.isAI ? 'ai-row' : (data.isMine ? 'user-row' : 'other-row');

    const row = document.createElement('div');
    row.className = 'message-row ' + rowClass + (isGrouped ? ' grouped' : '');
    if (animate) row.classList.add('msg-enter');
    if (data.id) row.setAttribute('data-msg-id', data.id);
    row.setAttribute('data-chat-kind', currentChatKind());

    const avatarHtml = isGrouped ? '<div class="msg-avatar-spacer"></div>' : avatarHtmlFor(data);

    const nameHtml = isGrouped ? '' : '<strong>' + escapeHtml(data.username) + '</strong>';

    const feedbackHtml = data.isAI ? buildFeedbackHtml(data) : '';
    const reactionHtml = (!data.isAI && data.id) ? buildReactionHtml(data) : '';

    row.innerHTML =
        avatarHtml +
        '<div class="message-bubble-wrap">' +
            nameHtml +
            '<div class="message">' + escapeHtml(data.message) + '</div>' +
            feedbackHtml +
            reactionHtml +
        '</div>';

    messagesBox.appendChild(row);
}

function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function clearEmptyState() {
    const empty = messagesBox.querySelector('.empty-state');
    if (empty) {
        messagesBox.innerHTML = '';
        lastRenderedKey = null;
    }
}

/* ---------- ULANISH HOLATI ---------- */
socket.on('connect', function () {
    isConnected = true;
    hideConnectionBanner();
});

socket.on('disconnect', function () {
    isConnected = false;
    showConnectionBanner('Aloqa uzildi, qayta ulanmoqda...');
});

socket.on('connect_error', function () {
    showConnectionBanner('Serverga ulanmoqda, iltimos kuting...');
});

function showConnectionBanner(text) {
    let banner = document.getElementById('conn-banner');
    if (!banner) {
        banner = document.createElement('div');
        banner.id = 'conn-banner';
        banner.className = 'conn-banner';
        document.querySelector('.main').insertBefore(banner, messagesBox);
    }
    banner.textContent = text;
}

function hideConnectionBanner() {
    const banner = document.getElementById('conn-banner');
    if (banner) banner.remove();
}

/* ---------- BILDIRISHNOMA TOAST ---------- */
function showNotificationToast(text) {
    const toast = document.createElement('div');
    toast.className = 'notf-toast';
    toast.textContent = text;
    document.body.appendChild(toast);
    setTimeout(function () { toast.classList.add('show'); }, 10);
    setTimeout(function () {
        toast.classList.remove('show');
        setTimeout(function () { toast.remove(); }, 300);
    }, 3500);
}

/* ---------- ANONIM XABAR CHEGARASI ---------- */
socket.on('anon_limit_update', function (data) {
    if (IS_LOGGED_IN) return;
    anonLimitBadge.style.display = 'inline-block';
    anonLimitBadge.textContent = data.remaining + ' ta bepul xabar qoldi';
    if (data.remaining <= 3) {
        anonLimitBadge.classList.add('anon-limit-warning');
    }
});

socket.on('login_required', function (data) {
    openLoginRequired();
});

function openLoginRequired() {
    document.getElementById('login-required-modal').classList.add('open');
}

function closeLoginRequired() {
    document.getElementById('login-required-modal').classList.remove('open');
}

socket.on('banned_notice', function (data) {
    alert(data.message);
});

socket.on('message_deleted', function (data) {
    const history = loadPublicHistory().filter(function (m) { return m.id !== data.id; });
    savePublicHistory(history);
    if (isPublicActive()) renderMessages();
});

/* ---------- SOCKET.IO: DO'STLIK BILDIRISHNOMALARI (real-vaqt) ---------- */
socket.on('friend_request_received', function (data) {
    loadFriendRequests();
    showNotificationToast(data.name + ' sizga dostlik taklifi yubordi');
    showBrowserNotification('Notfic', data.name + ' sizga dostlik taklifi yubordi');
});

socket.on('friend_request_accepted', function (data) {
    loadFriendsListModal();
    showNotificationToast(data.name + ' taklifingizni qabul qildi');
    showBrowserNotification('Notfic', data.name + ' taklifingizni qabul qildi');
});

socket.on('force_logout', function (data) {
    alert(data.reason === 'account_deleted'
        ? "Hisobingiz administrator tomonidan ochirildi."
        : "Hisobingiz bloklandi.");
    window.location.href = '/auth/logout';
});

socket.on('friend_removed', function (data) {
    loadFriendsListModal();
    if (getActiveChatId() === ('friend_' + data.user_id)) {
        switchToPublic();
        showNotificationToast('Bu foydalanuvchi sizni dostlar royxatidan chiqardi');
    }
});

socket.on('friend_online', function (data) {
    const dot = document.getElementById('friend-dot-' + data.user_id);
    if (dot) dot.classList.add('online');
});

socket.on('friend_offline', function (data) {
    const dot = document.getElementById('friend-dot-' + data.user_id);
    if (dot) dot.classList.remove('online');
});

socket.on('public_reaction_update', function (data) {
    const row = messagesBox.querySelector('.message-row[data-msg-id="' + data.id + '"]');
    if (row) {
        const reactionRow = row.querySelector('.msg-reaction-row');
        if (reactionRow) reactionRow.outerHTML = buildReactionHtml({ id: data.id, reaction: data.emoji });
    }
    const history = loadPublicHistory();
    const item = history.find(function (m) { return m.id === data.id; });
    if (item) {
        item.reaction = data.emoji;
        savePublicHistory(history);
    }
});

socket.on('friend_reaction_update', function (data) {
    const row = messagesBox.querySelector('.message-row[data-msg-id="' + data.id + '"]');
    if (row) {
        const reactionRow = row.querySelector('.msg-reaction-row');
        if (reactionRow) reactionRow.outerHTML = buildReactionHtml({ id: data.id, reaction: data.emoji });
    }
});

/* ---------- SOCKET.IO: AI SUHBATI (shaxsiy) ---------- */
socket.on('ai_response_message', function (data) {
    if (data.clientId && sentMessageIds.has(data.clientId)) {
        sentMessageIds.delete(data.clientId);
        return;
    }

    const chats = loadChats();
    let activeId = getActiveChatId();

    if (isPublicActive() || activeId.indexOf('friend_') === 0 || !chats[activeId]) {
        activeId = 'chat_' + Date.now();
        chats[activeId] = { id: activeId, title: 'Yangi AI suhbat', messages: [] };
        setActiveChatId(activeId);
    }

    const chat = chats[activeId];
    chat.messages.push(data);
    saveChats(chats);
    renderChatList();
    if (getActiveChatId() === activeId) {
        clearEmptyState();
        appendMessageToDOM(data, true);
        messagesBox.scrollTop = messagesBox.scrollHeight;
    }
    updateHeader();
    showBrowserNotification('Notfic', data.message.slice(0, 100));
});

socket.on('ai_typing', function (data) {
    if (data.typing) {
        showTypingIndicator();
    } else {
        hideTypingIndicator();
    }
});

function showTypingIndicator() {
    hideTypingIndicator();
    clearEmptyState();
    const row = document.createElement('div');
    row.className = 'message-row ai-row';
    row.id = 'typing-indicator';
    row.innerHTML =
        '<div class="msg-avatar msg-avatar-ai">⚡</div>' +
        '<div class="message-bubble-wrap">' +
            '<strong>Notfic</strong>' +
            '<div class="message typing-indicator"><span class="typing-dots"><span></span><span></span><span></span></span></div>' +
        '</div>';
    messagesBox.appendChild(row);
    lastRenderedKey = null;
    messagesBox.scrollTop = messagesBox.scrollHeight;
}

function hideTypingIndicator() {
    const el = document.getElementById('typing-indicator');
    if (el) el.remove();
}

/* ---------- SOCKET.IO: OCHIQ SUHBAT ---------- */
socket.on('public_response_message', function (data) {
    if (data.clientId && sentMessageIds.has(data.clientId)) {
        sentMessageIds.delete(data.clientId);
        return;
    }

    const history = loadPublicHistory();
    history.push(data);
    savePublicHistory(history);

    if (isPublicActive()) {
        clearEmptyState();
        appendMessageToDOM(data, true);
        messagesBox.scrollTop = messagesBox.scrollHeight;
    }
});

/* ---------- DO'STLAR BO'LIMI (yagona modal: sorovlar + royxat + qidirish) ---------- */
let searchDebounceTimer = null;

function openFriendsModal() {
    document.getElementById('friends-modal').classList.add('open');
    closeSidebar();
    loadFriendRequests();
    loadFriendsListModal();
}

function closeFriendsModal() {
    document.getElementById('friends-modal').classList.remove('open');
    const searchInput = document.getElementById('friend-search-input');
    const searchResults = document.getElementById('friend-search-results');
    if (searchInput) searchInput.value = '';
    if (searchResults) searchResults.innerHTML = '';
}

function searchFriends() {
    clearTimeout(searchDebounceTimer);
    const query = document.getElementById('friend-search-input').value.trim();
    const resultsEl = document.getElementById('friend-search-results');

    if (query.length < 2) {
        resultsEl.innerHTML = '';
        return;
    }

    searchDebounceTimer = setTimeout(async function () {
        try {
            const res = await fetch('/api/friends/search?q=' + encodeURIComponent(query));
            const users = await res.json();

            if (users.length === 0) {
                resultsEl.innerHTML = '<div class="sidebar-empty">Hech kim topilmadi</div>';
                return;
            }

            resultsEl.innerHTML = users.map(function (u) {
                let actionHtml = '';
                if (u.status === 'friends') {
                    actionHtml = '<span class="friend-status">Dostsiz</span>';
                } else if (u.status === 'pending_sent') {
                    actionHtml = '<span class="friend-status">Yuborilgan</span>';
                } else if (u.status === 'pending_received') {
                    actionHtml = '<span class="friend-status">Sizga taklif yuborgan</span>';
                } else {
                    actionHtml = '<button class="friend-add-btn" onclick="sendFriendRequest(' + u.id + ', this)">Taklif yuborish</button>';
                }

                const avatarHtml = u.avatar
                    ? '<img src="' + u.avatar + '" class="friend-result-avatar" alt="">'
                    : '<div class="friend-result-avatar profile-avatar-fallback">' + (u.name ? u.name[0] : '?') + '</div>';

                return '<div class="friend-result-item">' + avatarHtml +
                    '<span class="friend-result-name">' + escapeHtml(u.name) + '</span>' +
                    actionHtml + '</div>';
            }).join('');
        } catch (e) {
            console.error(e);
        }
    }, 300);
}

async function sendFriendRequest(userId, btnEl) {
    btnEl.disabled = true;
    btnEl.textContent = 'Yuborilmoqda...';

    try {
        const res = await fetch('/api/friends/request', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id: userId })
        });
        const data = await res.json();

        if (data.success) {
            btnEl.outerHTML = '<span class="friend-status">Yuborildi</span>';
        } else {
            btnEl.disabled = false;
            btnEl.textContent = 'Taklif yuborish';
        }
    } catch (e) {
        btnEl.disabled = false;
        btnEl.textContent = 'Taklif yuborish';
    }
}

async function loadFriendRequests() {
    try {
        const res = await fetch('/api/friends/requests');
        const requests = await res.json();

        const badge = document.getElementById('friend-request-badge');
        if (badge) {
            if (requests.length > 0) {
                badge.textContent = requests.length;
                badge.style.display = 'inline-flex';
            } else {
                badge.style.display = 'none';
            }
        }

        const el = document.getElementById('friend-requests-list');
        if (!el) return;

        if (requests.length === 0) {
            el.innerHTML = '';
            return;
        }

        el.innerHTML = requests.map(function (r) {
            const avatarHtml = r.avatar
                ? '<img src="' + r.avatar + '" class="friend-result-avatar" alt="">'
                : '<div class="friend-result-avatar profile-avatar-fallback">' + (r.name ? r.name[0] : '?') + '</div>';

            return '<div class="friend-request-item">' + avatarHtml +
                '<span class="friend-result-name">' + escapeHtml(r.name) + '</span>' +
                '<button class="friend-accept-btn" onclick="respondFriendRequest(' + r.request_id + ', \'accept\')">✓</button>' +
                '<button class="friend-reject-btn" onclick="respondFriendRequest(' + r.request_id + ', \'reject\')">✕</button>' +
                '</div>';
        }).join('');
    } catch (e) {
        console.error(e);
    }
}

async function respondFriendRequest(reqId, action) {
    try {
        await fetch('/api/friends/requests/' + reqId + '/respond', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action: action })
        });
        loadFriendRequests();
        if (action === 'accept') loadFriendsListModal();
    } catch (e) {
        console.error(e);
    }
}

async function loadFriendsListModal() {
    try {
        const res = await fetch('/api/friends');
        const friends = await res.json();
        cachedFriendsList = friends;

        const el = document.getElementById('friends-list-modal');
        if (!el) return;

        if (friends.length === 0) {
            el.innerHTML = '<div class="sidebar-empty">Hali dostlar yoq. Pastdan qidirib toping!</div>';
            return;
        }

        el.innerHTML = friends.map(function (f) {
            const avatarHtml = f.avatar
                ? '<img src="' + f.avatar + '" class="friend-result-avatar" alt="">'
                : '<div class="friend-result-avatar profile-avatar-fallback">' + (f.name ? f.name[0] : '?') + '</div>';

            return '<div class="friend-result-item">' +
                '<span class="friend-avatar-wrap">' + avatarHtml + '<span class="friend-online-dot' + (f.is_online ? ' online' : '') + '" id="friend-dot-' + f.id + '"></span></span>' +
                '<span class="friend-result-name">' + escapeHtml(f.name) + '</span>' +
                '<button class="friend-msg-btn" onclick="switchToFriendFromModal(' + f.id + ')">Yozish</button>' +
                '<button class="friend-remove-btn" onclick="removeFriend(' + f.id + ', this)" aria-label="Dostlikdan chiqarish">✕</button>' +
                '</div>';
        }).join('');
    } catch (e) {
        console.error(e);
    }
}

function switchToFriendFromModal(friendId) {
    const f = cachedFriendsList.find(function (x) { return x.id === friendId; });
    if (!f) return;
    switchToFriend(f.id, f.name, f.avatar);
    closeFriendsModal();
}

async function removeFriend(friendId, btnEl) {
    if (!confirm("Bu foydalanuvchini dostlar royxatidan ochirishni tasdiqlaysizmi?")) return;
    btnEl.disabled = true;

    try {
        const res = await fetch('/api/friends/' + friendId, { method: 'DELETE' });
        const data = await res.json();

        if (data.success) {
            loadFriendsListModal();
            if (getActiveChatId() === ('friend_' + friendId)) {
                switchToPublic();
            }
        } else {
            btnEl.disabled = false;
        }
    } catch (e) {
        console.error(e);
        btnEl.disabled = false;
    }
}

async function switchToFriend(friendId, friendName, friendAvatar) {
    setActiveChatId('friend_' + friendId);
    chatHeaderTitle.textContent = '👤 ' + friendName;
    document.getElementById('public-chat-item').classList.remove('active');
    closeSidebar();

    messagesBox.innerHTML = '<div class="empty-state"><p>Yuklanmoqda...</p></div>';
    lastRenderedKey = null;

    try {
        const res = await fetch('/api/friends/' + friendId + '/messages');
        const msgs = await res.json();

        messagesBox.innerHTML = '';
        lastRenderedKey = null;

        if (msgs.length === 0) {
            messagesBox.innerHTML = '<div class="empty-state"><h2>' + escapeHtml(friendName) + '</h2><p>Hali xabar yoq, birinchi bolib yozing 👋<br><span class="ai-hint">Suhbatga AI ni chaqirish uchun xabaringizga @AI deb yozing</span></p></div>';
            return;
        }

        msgs.forEach(function (m) {
            appendMessageToDOM({
                id: m.id,
                username: m.is_mine ? 'Siz' : friendName,
                message: m.message,
                avatar: m.avatar,
                isAI: false,
                isMine: m.is_mine,
                reaction: m.reaction
            }, false);
        });
        messagesBox.scrollTop = messagesBox.scrollHeight;
    } catch (e) {
        console.error(e);
    }
}

/* ---------- GURUH CHATLARI ---------- */
let cachedGroupsList = [];
let selectedGroupMemberIds = new Set();

function openGroupsModal() {
    document.getElementById('groups-modal').classList.add('open');
    closeSidebar();
    loadGroupsListModal();
    renderGroupMemberPicker();
}

function closeGroupsModal() {
    document.getElementById('groups-modal').classList.remove('open');
    document.getElementById('group-name-input').value = '';
    selectedGroupMemberIds.clear();
}

function renderGroupMemberPicker() {
    const el = document.getElementById('group-member-picker');
    if (!el) return;

    if (cachedFriendsList.length === 0) {
        el.innerHTML = '<div class="sidebar-empty">Guruh yaratish uchun avval dostlar qoshing</div>';
        return;
    }

    el.innerHTML = cachedFriendsList.map(function (f) {
        const avatarHtml = f.avatar
            ? '<img src="' + f.avatar + '" class="friend-result-avatar" alt="">'
            : '<div class="friend-result-avatar profile-avatar-fallback">' + (f.name ? f.name[0] : '?') + '</div>';

        return '<label class="group-member-option">' +
            '<input type="checkbox" onchange="toggleGroupMember(' + f.id + ', this.checked)">' +
            avatarHtml +
            '<span class="friend-result-name">' + escapeHtml(f.name) + '</span>' +
            '</label>';
    }).join('');
}

function toggleGroupMember(friendId, checked) {
    if (checked) {
        selectedGroupMemberIds.add(friendId);
    } else {
        selectedGroupMemberIds.delete(friendId);
    }
}

async function createGroup() {
    const nameInput = document.getElementById('group-name-input');
    const statusEl = document.getElementById('group-create-status');
    const name = nameInput.value.trim();

    if (selectedGroupMemberIds.size === 0) {
        statusEl.textContent = 'Kamida bitta dost tanlang';
        return;
    }

    statusEl.textContent = 'Yaratilmoqda...';

    try {
        const res = await fetch('/api/groups', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                name: name || 'Nomsiz guruh',
                member_ids: Array.from(selectedGroupMemberIds)
            })
        });
        const data = await res.json();

        if (data.success) {
            statusEl.textContent = '';
            nameInput.value = '';
            selectedGroupMemberIds.clear();
            renderGroupMemberPicker();
            loadGroupsListModal();
            switchToGroup(data.group_id, data.name);
            closeGroupsModal();
        } else {
            statusEl.textContent = 'Xato yuz berdi';
        }
    } catch (e) {
        statusEl.textContent = 'Xato yuz berdi';
    }
}

async function loadGroupsListModal() {
    try {
        const res = await fetch('/api/groups');
        const groups = await res.json();
        cachedGroupsList = groups;

        const el = document.getElementById('groups-list-modal');
        if (!el) return;

        if (groups.length === 0) {
            el.innerHTML = '<div class="sidebar-empty">Hali guruhlar yoq</div>';
            return;
        }

        el.innerHTML = groups.map(function (g) {
            return '<div class="friend-result-item">' +
                '<div class="friend-result-avatar profile-avatar-fallback">👥</div>' +
                '<span class="friend-result-name">' + escapeHtml(g.name) + ' <span class="group-member-count">(' + g.member_count + ')</span></span>' +
                '<button class="friend-msg-btn" onclick="switchToGroupFromModal(' + g.id + ')">Ochish</button>' +
                '</div>';
        }).join('');
    } catch (e) {
        console.error(e);
    }
}

function switchToGroupFromModal(groupId) {
    const g = cachedGroupsList.find(function (x) { return x.id === groupId; });
    if (!g) return;
    switchToGroup(g.id, g.name);
    closeGroupsModal();
}

async function switchToGroup(groupId, groupName) {
    setActiveChatId('group_' + groupId);
    chatHeaderTitle.textContent = '👥 ' + groupName;
    document.getElementById('public-chat-item').classList.remove('active');
    closeSidebar();

    messagesBox.innerHTML = '<div class="empty-state"><p>Yuklanmoqda...</p></div>';
    lastRenderedKey = null;

    try {
        const res = await fetch('/api/groups/' + groupId + '/messages');
        const msgs = await res.json();

        messagesBox.innerHTML = '';
        lastRenderedKey = null;

        if (msgs.length === 0) {
            messagesBox.innerHTML = '<div class="empty-state"><h2>' + escapeHtml(groupName) + '</h2><p>Hali xabar yoq, birinchi bolib yozing 👋<br><span class="ai-hint">AI ni chaqirish uchun @AI deb yozing</span></p></div>';
            return;
        }

        msgs.forEach(function (m) {
            appendMessageToDOM({
                id: m.id,
                username: m.is_mine ? 'Siz' : m.sender_name,
                message: m.message,
                avatar: m.sender_avatar,
                isAI: !!m.is_ai,
                isMine: !!m.is_mine
            }, false);
        });
        messagesBox.scrollTop = messagesBox.scrollHeight;
    } catch (e) {
        console.error(e);
    }
}

socket.on('group_created', function (data) {
    loadGroupsListModal();
    showNotificationToast("Sizni \"" + data.name + "\" guruhiga qoshishdi");
});

socket.on('group_message', function (data) {
    if (data.clientId && sentMessageIds.has(data.clientId)) {
        sentMessageIds.delete(data.clientId);
        return;
    }

    const activeId = getActiveChatId();
    if (activeId === ('group_' + data.group_id)) {
        clearEmptyState();
        appendMessageToDOM({
            username: data.sender_name,
            message: data.message,
            avatar: data.sender_avatar,
            isAI: !!data.is_ai,
            prompt: data.prompt
        }, true);
        messagesBox.scrollTop = messagesBox.scrollHeight;
    } else if (!data.is_ai) {
        showNotificationToast(data.sender_name + ' (guruh): ' + data.message.slice(0, 60));
        showBrowserNotification(data.sender_name + ' (guruh)', data.message.slice(0, 100));
    }
});

/* ---------- ADMINGA MUROJAAT ---------- */
function openSupportModal() {
    document.getElementById('support-modal').classList.add('open');
}

function closeSupportModal() {
    document.getElementById('support-modal').classList.remove('open');
}

async function sendSupportMessage() {
    const input = document.getElementById('support-message-input');
    const statusEl = document.getElementById('support-status');
    const message = input.value.trim();

    if (!message) return;

    statusEl.textContent = 'Yuborilmoqda...';

    try {
        const res = await fetch('/api/support', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: message })
        });
        const data = await res.json();

        if (data.success) {
            statusEl.textContent = 'Yuborildi ✓ Tez orada koriladi';
            input.value = '';
            setTimeout(function () {
                statusEl.textContent = '';
                closeSupportModal();
            }, 2000);
        } else {
            statusEl.textContent = 'Xato yuz berdi';
        }
    } catch (e) {
        statusEl.textContent = 'Xato yuz berdi';
    }
}

socket.on('friend_message', function (data) {
    if (data.clientId && sentMessageIds.has(data.clientId)) {
        sentMessageIds.delete(data.clientId);
        return;
    }

    const activeId = getActiveChatId();
    const otherUserId = (activeId.indexOf('friend_') === 0) ? parseInt(activeId.replace('friend_', ''), 10) : null;

    const belongsToConversation = (otherUserId === data.from_user_id || otherUserId === data.to_user_id);

    if (belongsToConversation) {
        clearEmptyState();
        appendMessageToDOM({
            username: data.sender_name,
            message: data.message,
            avatar: data.sender_avatar,
            isAI: !!data.isAI,
            prompt: data.prompt
        }, true);
        messagesBox.scrollTop = messagesBox.scrollHeight;
    } else if (!data.isAI && data.sender_name) {
        showNotificationToast(data.sender_name + ': ' + data.message.slice(0, 60));
        showBrowserNotification(data.sender_name, data.message.slice(0, 100));
    }
});

/* ---------- XABAR YUBORISH ---------- */
function sendMessage() {
    const usernameInput = document.getElementById('username');
    const messageInput = document.getElementById('message-input');

    const username = IS_LOGGED_IN
        ? (document.querySelector('.profile-name') ? document.querySelector('.profile-name').textContent.trim() : 'Foydalanuvchi')
        : (usernameInput.value.trim() || 'Anonim');

    const message = messageInput.value.trim();

    if (message === '') return;

    const activeId = getActiveChatId();
    const clientId = 'msg_' + Date.now() + '_' + Math.random().toString(36).slice(2, 8);
    sentMessageIds.add(clientId);

    if (activeId.indexOf('friend_') === 0) {
        const friendId = parseInt(activeId.replace('friend_', ''), 10);
        clearEmptyState();
        const myAvatar = document.getElementById('sidebar-avatar-img');
        appendMessageToDOM({
            username: 'Siz',
            message: message,
            avatar: (myAvatar && myAvatar.tagName === 'IMG') ? myAvatar.src : null,
            isAI: false,
            isMine: true
        }, true);
        messagesBox.scrollTop = messagesBox.scrollHeight;
        socket.emit('friend_message', { to_user_id: friendId, message: message, clientId: clientId });
        messageInput.value = '';
        return;
    }

    if (activeId.indexOf('group_') === 0) {
        const groupId = parseInt(activeId.replace('group_', ''), 10);
        clearEmptyState();
        const myAvatar = document.getElementById('sidebar-avatar-img');
        appendMessageToDOM({
            username: 'Siz',
            message: message,
            avatar: (myAvatar && myAvatar.tagName === 'IMG') ? myAvatar.src : null,
            isAI: false,
            isMine: true
        }, true);
        messagesBox.scrollTop = messagesBox.scrollHeight;
        socket.emit('group_message', { group_id: groupId, message: message, clientId: clientId });
        messageInput.value = '';
        return;
    }

    const myAvatarEl = document.getElementById('sidebar-avatar-img');
    const myAvatar = (myAvatarEl && myAvatarEl.tagName === 'IMG') ? myAvatarEl.src : null;

    const localData = { username: username, message: message, avatar: myAvatar, isAI: false, isMine: true, clientId: clientId };

    clearEmptyState();
    appendMessageToDOM(localData, true);
    messagesBox.scrollTop = messagesBox.scrollHeight;

    if (isPublicActive()) {
        const history = loadPublicHistory();
        history.push(localData);
        savePublicHistory(history);
        socket.emit('public_message', { username: username, message: message, clientId: clientId });
    } else {
        const chats = loadChats();
        let chatId = activeId;
        if (!chats[chatId]) {
            chatId = 'chat_' + Date.now();
            chats[chatId] = { id: chatId, title: 'Yangi AI suhbat', messages: [] };
            setActiveChatId(chatId);
        }
        const chat = chats[chatId];

        // AI'ga oldingi xabarlarni kontekst sifatida yuboramiz (oxirgi 14 tasi)
        const context = chat.messages.slice(-14);

        chat.messages.push(localData);
        if (chat.title === 'Yangi AI suhbat') {
            chat.title = message.slice(0, 28) + (message.length > 28 ? '...' : '');
        }
        saveChats(chats);
        renderChatList();
        updateHeader();

        socket.emit('ai_message', { username: username, message: message, clientId: clientId, context: context });
    }

    messageInput.value = '';
}

/* ---------- SOZLAMALAR / MAVZU ---------- */
/* ---------- BRAUZER BILDIRISHNOMALARI ---------- */
const NOTIF_PREF_KEY = 'notfic_notifications_enabled';

function notificationsEnabled() {
    return localStorage.getItem(NOTIF_PREF_KEY) === 'true' && 'Notification' in window && Notification.permission === 'granted';
}

async function enableBrowserNotifications() {
    if (!('Notification' in window)) {
        alert('Brauzeringiz bildirishnomalarni qollab-quvvatlamaydi.');
        return;
    }
    const permission = await Notification.requestPermission();
    if (permission === 'granted') {
        localStorage.setItem(NOTIF_PREF_KEY, 'true');
        showBrowserNotification('Notfic', 'Bildirishnomalar yoqildi ✓', true);
    } else {
        localStorage.setItem(NOTIF_PREF_KEY, 'false');
    }
    updateNotifSettingsUI();
}

function disableBrowserNotifications() {
    localStorage.setItem(NOTIF_PREF_KEY, 'false');
    updateNotifSettingsUI();
}

function updateNotifSettingsUI() {
    const label = document.getElementById('notif-toggle-label');
    const btn = document.getElementById('notif-toggle-btn');
    if (!label || !btn) return;

    const enabled = notificationsEnabled();
    label.textContent = enabled ? 'Yoqilgan' : "Ochirilgan";
    btn.onclick = enabled ? disableBrowserNotifications : enableBrowserNotifications;
}

function showBrowserNotification(title, body, force) {
    if (!notificationsEnabled()) return;
    if (!force && document.visibilityState === 'visible' && document.hasFocus()) return;

    try {
        const n = new Notification(title, { body: body, tag: 'notfic-' + Date.now() });
        n.onclick = function () {
            window.focus();
            n.close();
        };
    } catch (e) {
        console.error(e);
    }
}

function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem(THEME_KEY, theme);
    const label = document.getElementById('theme-label');
    if (label) label.textContent = theme === 'dark' ? 'Qorongi rang' : 'Och rang';
}

function toggleTheme() {
    const current = localStorage.getItem(THEME_KEY) || 'light';
    applyTheme(current === 'light' ? 'dark' : 'light');
}

function openSettings() {
    document.getElementById('settings-modal').classList.add('open');
}

function closeSettings() {
    document.getElementById('settings-modal').classList.remove('open');
}

/* ---------- PROFIL MODAL ---------- */
function openProfile() {
    const modal = document.getElementById('profile-modal');
    if (modal) modal.classList.add('open');
}

function closeProfile() {
    const modal = document.getElementById('profile-modal');
    if (modal) modal.classList.remove('open');
}

async function saveProfile() {
    const nameInput = document.getElementById('profile-name-input');
    const bioInput = document.getElementById('profile-bio-input');
    const statusEl = document.getElementById('profile-save-status');

    statusEl.textContent = 'Saqlanmoqda...';

    try {
        const res = await fetch('/api/profile', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: nameInput.value, bio: bioInput.value })
        });
        const data = await res.json();

        if (data.success) {
            statusEl.textContent = 'Saqlandi ✓';
            const nameEl = document.querySelector('.profile-name');
            if (nameEl) nameEl.textContent = data.name;
            setTimeout(function () { statusEl.textContent = ''; }, 2000);
        } else {
            statusEl.textContent = 'Xato yuz berdi';
        }
    } catch (e) {
        statusEl.textContent = 'Xato yuz berdi';
    }
}

/* ---------- AVATAR YUKLASH ---------- */
async function uploadAvatar(input) {
    const file = input.files[0];
    if (!file) return;

    const statusEl = document.getElementById('avatar-upload-status');
    statusEl.textContent = 'Yuklanmoqda...';

    const formData = new FormData();
    formData.append('avatar', file);

    try {
        const res = await fetch('/api/profile/avatar', {
            method: 'POST',
            body: formData
        });
        const data = await res.json();

        if (data.success) {
            updateAvatarImages(data.avatar);
            statusEl.textContent = 'Rasm yangilandi ✓';
            setTimeout(function () { statusEl.textContent = ''; }, 2000);
        } else {
            statusEl.textContent = data.message || 'Xato yuz berdi';
        }
    } catch (e) {
        statusEl.textContent = 'Xato yuz berdi';
    }

    input.value = '';
}

async function removeAvatar() {
    const statusEl = document.getElementById('avatar-upload-status');
    statusEl.textContent = 'Ozgartirilmoqda...';

    try {
        const res = await fetch('/api/profile/avatar', { method: 'DELETE' });
        const data = await res.json();

        if (data.success) {
            updateAvatarImages(data.avatar);
            statusEl.textContent = 'Odatiy rasmga qaytarildi ✓';
            setTimeout(function () { statusEl.textContent = ''; }, 2000);
        }
    } catch (e) {
        statusEl.textContent = 'Xato yuz berdi';
    }
}

function updateAvatarImages(url) {
    const sidebarImg = document.getElementById('sidebar-avatar-img');
    const profileImg = document.getElementById('profile-avatar-img');

    [sidebarImg, profileImg].forEach(function (el) {
        if (!el) return;
        if (el.tagName === 'IMG') {
            el.src = url;
        } else {
            const img = document.createElement('img');
            img.src = url;
            img.className = el.className.replace('profile-avatar-fallback', '').trim();
            img.id = el.id;
            el.replaceWith(img);
        }
    });
}

/* ---------- BOSHLANG'ICH YUKLASH ---------- */
/* ---------- PWA: ILOVA SIFATIDA O'RNATISH ---------- */
const INSTALL_DISMISS_KEY = 'notfic_install_dismissed';
let deferredInstallPrompt = null;

if ('serviceWorker' in navigator) {
    window.addEventListener('load', function () {
        navigator.serviceWorker.register('/sw.js').catch(function (e) {
            console.error('Service worker royxatga olinmadi:', e);
        });
    });
}

function isIosDevice() {
    return /iphone|ipad|ipod/.test(window.navigator.userAgent.toLowerCase());
}

function isStandaloneMode() {
    return window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone === true;
}

function showInstallBanner() {
    if (localStorage.getItem(INSTALL_DISMISS_KEY) === 'true') return;
    if (isStandaloneMode()) return;
    const banner = document.getElementById('install-banner');
    if (banner) banner.classList.add('show');
}

function showIosInstallBanner() {
    const text = document.getElementById('install-banner-text');
    const btn = document.getElementById('install-banner-btn');
    if (text) text.textContent = "Pastdagi Ulashish tugmasini bosib, 'Bosh ekranga qoshish'ni tanlang.";
    if (btn) btn.style.display = 'none';
    showInstallBanner();
}

function dismissInstallBanner() {
    localStorage.setItem(INSTALL_DISMISS_KEY, 'true');
    const banner = document.getElementById('install-banner');
    if (banner) banner.classList.remove('show');
}

async function installApp() {
    if (!deferredInstallPrompt) return;
    deferredInstallPrompt.prompt();
    await deferredInstallPrompt.userChoice;
    deferredInstallPrompt = null;
    dismissInstallBanner();
}

window.addEventListener('beforeinstallprompt', function (event) {
    event.preventDefault();
    deferredInstallPrompt = event;
    showInstallBanner();
});

window.addEventListener('appinstalled', function () {
    dismissInstallBanner();
});

window.addEventListener('DOMContentLoaded', function() {
    applyTheme(localStorage.getItem(THEME_KEY) || 'light');
    updateNotifSettingsUI();

    const chats = loadChats();
    const chatIds = Object.keys(chats).sort(function (a, b) { return b.localeCompare(a); });
    if (chatIds.length > 0) {
        setActiveChatId(chatIds[0]);
    } else {
        setActiveChatId('chat_' + Date.now());
    }

    renderChatList();
    renderMessages();
    updateHeader();

    if (isIosDevice() && !isStandaloneMode()) {
        setTimeout(showIosInstallBanner, 1500);
    }

    if (!IS_LOGGED_IN) {
        const savedUsername = localStorage.getItem('notfic_username');
        if (savedUsername) document.getElementById('username').value = savedUsername;

        document.getElementById('username').addEventListener('change', function (e) {
            localStorage.setItem('notfic_username', e.target.value);
        });
    } else {
        loadFriendRequests();
        // Push orqali real-vaqt bildirishnomalar keladi; bu faqat zaxira uchun
        setInterval(loadFriendRequests, 60000);
    }
});