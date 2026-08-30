const axios = require('axios');
const config = require('../config');

const sendTelegramNotification = async (title, message, color = 'info') => {
    const { telegramToken, telegramChatId } = config;
    
    if (!telegramToken || !telegramChatId) {
        console.log('❌ Telegram chưa được cấu hình');
        return false;
    }
    
    const icons = {
        success: '✅',
        error: '❌',
        warning: '⚠️',
        info: '📢',
        deposit: '💰',
        withdraw: '💸',
    };
    const icon = icons[color] || '📢';
    
    const fullMessage = `${icon} *${title}*\n\n${message}`;
    
    try {
        const url = `https://api.telegram.org/bot${telegramToken}/sendMessage`;
        await axios.post(url, {
            chat_id: telegramChatId,
            text: fullMessage,
            parse_mode: 'Markdown',
        });
        return true;
    } catch (error) {
        console.error('Lỗi gửi Telegram:', error.message);
        return false;
    }
};

module.exports = {
    sendTelegramNotification,
};