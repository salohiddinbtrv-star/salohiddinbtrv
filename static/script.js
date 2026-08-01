const socket = io();
const messagesBox = document.getElementById('messages-box');
const chatList = document.getElementById('chat-list');

const STORAGE_KEY = 'notfic_chats';
const ACTIVE_KEY = 'notfic_active_chat';
const THEME_KEY = 'notfic_theme';

function loadChats() {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}');
}

function saveChats(chats) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(chats));
}

function getActiveChatId() {
    return localStorage.getItem(ACTIVE_KEY);
}

function setActiveChatId(id) {
    localStorage.setItem(ACTIVE_KEY, id);
}

function newChat() {
    const chats = loadChats();
    const id = 'chat_' + Date.now();
    chats[id] = { id: id, title: 'Yangi suhbat', messages: [] };
    saveChats(chats);
    setActiveChatId(id);
    renderChatList();
    renderMessages();
}

function renderChatList() {
    const chats = loadChats();
    const activeId = getActiveChatId();
    const ids = Object.keys(chats).sort(function(a, b) { return b.localeCompare(a); });

    chatList.innerHTML = '';

    if (ids.length === 0) {
        chatList.innerHTML = '<span class="sidebar-empty">Hali suhbat yoq</span>';
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
            };
        })(id);
        chatList.appendChild(item);
    }
}

function renderMessages() {
    const chats = loadChats();
    const chat = chats[getActiveChatId()];

    messagesBox.innerHTML = '';

    if (!chat || chat.messages.length === 0) {
        messagesBox.innerHTML = '<div class="empty-state"><h2>Nima bilan yordam beray?</h2><p>Savolingizni pastga yozing va Enter bosing.</p></div>';
        return;
    }

    for (let i = 0; i < chat.messages.length; i++) {
        appendMessageToDOM(chat.messages[i]);
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

function saveMessageToActiveChat(data) {
    const chats = loadChats();
    let activeId = getActiveChatId();

    if (!activeId || !chats[activeId]) {
        activeId = 'chat_' + Date.now();
        chats[activeId] = { id: activeId, title: 'Yangi suhbat', messages: [] };
        setActiveChatId(activeId);
    }

    const chat = chats[activeId];
    chat.messages.push(data);

    if (chat.title === 'Yangi suhbat' && !data.isAI) {
        chat.title = data.message.slice(0, 28) + (data.message.length > 28 ? '...' : '');
    }

    saveChats(chats);
    renderChatList();
}

socket.on('response_message', function (data) {
    const isAI = data.username === 'Notfic AI ⚡';
    saveMessageToActiveChat({ username: data.username, message: data.message, isAI: isAI });
    renderMessages();
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

function sendMessage() {
    const usernameInput = document.getElementById('username');
    const messageInput = document.getElementById('message-input');

    const username = usernameInput.value.trim() || 'Anonim';
    const message = messageInput.value.trim();

    if (message !== '') {
        if (!getActiveChatId() || !loadChats()[getActiveChatId()]) newChat();
        socket.emit('message', { username: username, message: message });
        messageInput.value = '';
    }
}

function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem(THEME_KEY, theme);
    const label = document.getElementById('theme-label');
    if (label) {
        label.textContent = theme === 'dark' ? 'Qorongi rang' : 'Och rang';
    }
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

window.addEventListener('DOMContentLoaded', function() {
    applyTheme(localStorage.getItem(THEME_KEY) || 'light');

    const chats = loadChats();
    if (Object.keys(chats).length === 0 || !chats[getActiveChatId()]) {
        newChat();
    } else {
        renderChatList();
        renderMessages();
    }

    const savedUsername = localStorage.getItem('notfic_username');
    if (savedUsername) {
        document.getElementById('username').value = savedUsername;
    }

    document.getElementById('username').addEventListener('change', function(e) {
        localStorage.setItem('notfic_username', e.target.value);
    });
});