// utils/helpers.js
const moment = require('moment-timezone');
const config = require('../config');

const formatPrice = (amount) => {
    if (!amount) return '0đ';
    return Number(amount).toLocaleString('vi-VN') + 'đ';
};

const formatDate = (date, format = 'DD/MM/YYYY HH:mm') => {
    if (!date) return '';
    return moment(date).tz(config.timezone).format(format);
};

const generateCode = (prefix = '', length = 6) => {
    const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';
    let code = '';
    for (let i = 0; i < length; i++) {
        code += chars.charAt(Math.floor(Math.random() * chars.length));
    }
    return prefix ? `${prefix}_${code}` : code;
};

const generateOTP = () => {
    return Math.floor(100000 + Math.random() * 900000).toString();
};

const getVietnamTime = () => {
    return moment().tz(config.timezone);
};

const formatVietnamTime = (date) => {
    return moment(date).tz(config.timezone).format('DD/MM/YYYY HH:mm:ss');
};

const calculateCommission = (amount, rate = config.commissionRate) => {
    return {
        seller: amount * rate,
        admin: amount * (1 - rate),
    };
};

const generateVietQR = (accountNo, accountName, bankId, amount, description) => {
    const encodedDesc = encodeURIComponent(description);
    const encodedName = encodeURIComponent(accountName);
    return `https://img.vietqr.io/image/${bankId}-${accountNo}-qr_only.png?amount=${Math.floor(amount)}&addInfo=${encodedDesc}&accountName=${encodedName}`;
};

module.exports = {
    formatPrice,
    formatDate,
    generateCode,
    generateOTP,
    getVietnamTime,
    formatVietnamTime,
    calculateCommission,
    generateVietQR,
};
