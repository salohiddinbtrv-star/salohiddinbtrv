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

/* ---------- MOBIL BALANDLIK TUZATISH (klaviatura muammosi) ---------- */
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
        const chats = loadChats();
        const chat = chats[getActiveChatId()];
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
    messagesBox.innerHTML = '';

    if (isPublicActive()) {
        const history = loadPublicHistory();
        if (history.length === 0) {
            messagesBox.innerHTML = '<div class="empty-state"><h2>Ochiq Suhbat</h2><p>Bu yerga yozgan xabaringizni saytdagi hamma korishi mumkin.</p></div>';
            return;
        }
        history.forEach(appendMessageToDOM);
    } else {
        const chats = loadChats();
        const chat = chats[getActiveChatId()];
        if (!chat || chat.messages.length === 0) {
            messagesBox.innerHTML = '<div class="empty-state"><h2>Nima bilan yordam beray?</h2><p>Bu suhbat faqat sizga korinadi.</p></div>';
            return;
        }
        chat.messages.forEach(appendMessageToDOM);
    }

    messagesBox.scrollTop = messagesBox.scrollHeight;
}

function appendMessageToDOM(data) {
    const el = document.createElement('div');
    el.classList.add('message');
    if (data.isAI) el.classList.add('ai-message');
    el.innerHTML = '<strong>' + escapeHtml(data.username) + ':</strong> ' + escapeHtml(data.message);
    messagesBox.appendChild(el);
}

function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function clearEmptyState() {
    const empty = messagesBox.querySelector('.empty-state');
    if (empty) messagesBox.innerHTML = '';
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

/* ---------- SOCKET.IO: AI SUHBATI (shaxsiy) ---------- */
socket.on('ai_response_message', function (data) {
    if (data.clientId && sentMessageIds.has(data.clientId)) {
        sentMessageIds.delete(data.clientId);
        return;
    }

    const chats = loadChats();
    let activeId = getActiveChatId();

    if (isPublicActive() || !chats[activeId]) {
        activeId = 'chat_' + Date.now();
        chats[activeId] = { id: activeId, title: 'Yangi AI suhbat', messages: [] };
        setActiveChatId(activeId);
    }

    const chat = chats[activeId];
    chat.messages.push(data);
    saveChats(chats);
    renderChatList();
    if (!isPublicActive()) renderMessages();
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
    const el = document.createElement('div');
    el.className = 'message ai-message typing-indicator';
    el.id = 'typing-indicator';
    el.innerHTML = '<strong>Notfic AI ⚡:</strong> <span class="typing-dots"><span></span><span></span><span></span></span>';
    messagesBox.appendChild(el);
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
        appendMessageToDOM(data);
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

    const clientId = 'msg_' + Date.now() + '_' + Math.random().toString(36).slice(2, 8);
    sentMessageIds.add(clientId);

    const localData = { username: username, message: message, isAI: false, clientId: clientId };

    clearEmptyState();
    appendMessageToDOM(localData);
    messagesBox.scrollTop = messagesBox.scrollHeight;

    if (isPublicActive()) {
        const history = loadPublicHistory();
        history.push(localData);
        savePublicHistory(history);
        socket.emit('public_message', { username: username, message: message, clientId: clientId });
    } else {
        const chats = loadChats();
        let activeId = getActiveChatId();
        if (!chats[activeId]) {
            activeId = 'chat_' + Date.now();
            chats[activeId] = { id: activeId, title: 'Yangi AI suhbat', messages: [] };
            setActiveChatId(activeId);
        }
        const chat = chats[activeId];
        chat.messages.push(localData);
        if (chat.title === 'Yangi AI suhbat') {
            chat.title = message.slice(0, 28) + (message.length > 28 ? '...' : '');
        }
        saveChats(chats);
        renderChatList();
        updateHeader();

        socket.emit('ai_message', { username: username, message: message, clientId: clientId });
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

    if (!localStorage.getItem(ACTIVE_KEY)) {
        setActiveChatId(PUBLIC_ID);
    }

    renderChatList();
    renderMessages();
    updateHeader();

    if (!IS_LOGGED_IN) {
        const savedUsername = localStorage.getItem('notfic_username');
        if (savedUsername) document.getElementById('username').value = savedUsername;

        document.getElementById('username').addEventListener('change', function (e) {
            localStorage.setItem('notfic_username', e.target.value);
        });
    }
});