const socket = io();
const messagesBox = document.getElementById('messages-box');

socket.on('response_message', function(data) {
    const msgElement = document.createElement('div');
    msgElement.classList.add('message');
    
    if (data.username === 'Notfic AI') {
        msgElement.classList.add('ai-message');
    }

    msgElement.innerHTML = `<strong>${data.username}:</strong> ${data.message}`;
    messagesBox.appendChild(msgElement);
    messagesBox.scrollTop = messagesBox.scrollHeight;
});

function sendMessage() {
    const usernameInput = document.getElementById('username');
    const messageInput = document.getElementById('message-input');

    const username = usernameInput.value.trim() || 'Anonim';
    const message = messageInput.value.trim();

    if (message !== '') {
        socket.emit('message', { username: username, message: message });
        messageInput.value = '';
    }
}