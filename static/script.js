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

function renderChatList() {
    const chats = loadChats();
    const activeId = getActiveChatId();
    const ids = Object.keys(chats).sort(function(a, b) { return b.localeCompare(a); });

    chatList.innerHTML = '';

    if (ids.length === 0) {
        chatList.innerHTML = '<span class="sidebar-empty">Hali AI suhbat yoq</span>';
        return;
    }

    for (let i = 0; i < ids.length; i++) {
        const id = ids[i];
        const chat = chats[id];
        const item = document.createElement('div');
        item.className = 'chat-item' + (id === activeId ? ' active' : '');
        item.textContent = chat.title;
        item.onclick = (function(chatId) {
            return function() {
                setActiveChatId(chatId);
                renderChatList();
                renderMessages();
                updateHeader();
                closeSidebar();
            };
        })(id);
        chatList.appendChild(item);
    }
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

function appendMessageToDOM(data, animate) {
    const groupKey = (data.isAI ? 'ai' : 'user') + '::' + data.username;
    const isGrouped = (groupKey === lastRenderedKey);
    lastRenderedKey = groupKey;

    const row = document.createElement('div');
    row.className = 'message-row' + (data.isAI ? ' ai-row' : ' user-row') + (isGrouped ? ' grouped' : '');
    if (animate) row.classList.add('msg-enter');
    if (data.id) row.setAttribute('data-msg-id', data.id);

    const avatarHtml = isGrouped ? '<div class="msg-avatar-spacer"></div>' : avatarHtmlFor(data);

    const nameHtml = isGrouped ? '' : '<strong>' + escapeHtml(data.username) + '</strong>';

    row.innerHTML =
        avatarHtml +
        '<div class="message-bubble-wrap">' +
            nameHtml +
            '<div class="message">' + escapeHtml(data.message) + '</div>' +
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
            '<strong>Notfic AI</strong>' +
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

/* ---------- DO'STLIK TIZIMI ---------- */
let searchDebounceTimer = null;

function openFriendSearch() {
    document.getElementById('friend-search-modal').classList.add('open');
    document.getElementById('friend-search-input').focus();
}

function closeFriendSearch() {
    document.getElementById('friend-search-modal').classList.remove('open');
    document.getElementById('friend-search-input').value = '';
    document.getElementById('friend-search-results').innerHTML = '';
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
        if (action === 'accept') loadFriendsList();
    } catch (e) {
        console.error(e);
    }
}

async function loadFriendsList() {
    try {
        const res = await fetch('/api/friends');
        const friends = await res.json();
        const el = document.getElementById('friends-list');
        if (!el) return;

        if (friends.length === 0) {
            el.innerHTML = '<span class="sidebar-empty">Hali dostlar yoq</span>';
            return;
        }

        el.innerHTML = '';
        friends.forEach(function (f) {
            const item = document.createElement('div');
            item.className = 'chat-item' + (getActiveChatId() === ('friend_' + f.id) ? ' active' : '');
            item.textContent = f.name;
            item.onclick = function () {
                switchToFriend(f.id, f.name, f.avatar);
            };
            el.appendChild(item);
        });
    } catch (e) {
        console.error(e);
    }
}

async function switchToFriend(friendId, friendName, friendAvatar) {
    setActiveChatId('friend_' + friendId);
    chatHeaderTitle.textContent = '👤 ' + friendName;
    document.getElementById('public-chat-item').classList.remove('active');
    loadFriendsList();
    closeSidebar();

    messagesBox.innerHTML = '<div class="empty-state"><p>Yuklanmoqda...</p></div>';
    lastRenderedKey = null;

    try {
        const res = await fetch('/api/friends/' + friendId + '/messages');
        const msgs = await res.json();

        messagesBox.innerHTML = '';
        lastRenderedKey = null;

        if (msgs.length === 0) {
            messagesBox.innerHTML = '<div class="empty-state"><h2>' + escapeHtml(friendName) + '</h2><p>Hali xabar yoq, birinchi bolib yozing 👋</p></div>';
            return;
        }

        msgs.forEach(function (m) {
            appendMessageToDOM({
                username: m.is_mine ? 'Siz' : friendName,
                message: m.message,
                avatar: m.avatar,
                isAI: false
            }, false);
        });
        messagesBox.scrollTop = messagesBox.scrollHeight;
    } catch (e) {
        console.error(e);
    }
}

socket.on('friend_message', function (data) {
    if (data.clientId && sentMessageIds.has(data.clientId)) {
        sentMessageIds.delete(data.clientId);
        return;
    }

    const activeId = getActiveChatId();
    const otherUserId = (activeId.indexOf('friend_') === 0) ? parseInt(activeId.replace('friend_', ''), 10) : null;

    if (otherUserId === data.from_user_id || otherUserId === data.to_user_id) {
        clearEmptyState();
        appendMessageToDOM({
            username: data.sender_name,
            message: data.message,
            avatar: data.sender_avatar,
            isAI: false
        }, true);
        messagesBox.scrollTop = messagesBox.scrollHeight;
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
            isAI: false
        }, true);
        messagesBox.scrollTop = messagesBox.scrollHeight;
        socket.emit('friend_message', { to_user_id: friendId, message: message, clientId: clientId });
        messageInput.value = '';
        return;
    }

    const myAvatarEl = document.getElementById('sidebar-avatar-img');
    const myAvatar = (myAvatarEl && myAvatarEl.tagName === 'IMG') ? myAvatarEl.src : null;

    const localData = { username: username, message: message, avatar: myAvatar, isAI: false, clientId: clientId };

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
window.addEventListener('DOMContentLoaded', function() {
    applyTheme(localStorage.getItem(THEME_KEY) || 'light');

    setActiveChatId(PUBLIC_ID);

    renderChatList();
    renderMessages();
    updateHeader();

    if (!IS_LOGGED_IN) {
        const savedUsername = localStorage.getItem('notfic_username');
        if (savedUsername) document.getElementById('username').value = savedUsername;

        document.getElementById('username').addEventListener('change', function (e) {
            localStorage.setItem('notfic_username', e.target.value);
        });
    } else {
        loadFriendRequests();
        loadFriendsList();
        setInterval(loadFriendRequests, 15000);
    }
});