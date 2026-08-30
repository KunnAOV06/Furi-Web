// utils/email.js
const nodemailer = require('nodemailer');
const config = require('../config');

const transporter = nodemailer.createTransport({
    host: config.email.host,
    port: config.email.port,
    secure: config.email.port === 465,
    auth: {
        user: config.email.user,
        pass: config.email.pass,
    },
});

const sendEmailOTP = async (toEmail, otpCode, username) => {
    try {
        const html = `
        <!DOCTYPE html>
        <html>
        <head><meta charset="UTF-8"></head>
        <body style="font-family: 'Inter', sans-serif; background: #0a0a0f; color: #f0f0ff; padding: 20px;">
            <div style="max-width: 500px; margin: 0 auto; background: #111118; border-radius: 16px; padding: 30px; border: 1px solid #2a2a3a;">
                <div style="text-align: center; margin-bottom: 20px;">
                    <h1 style="background: linear-gradient(135deg, #ff1744, #2979ff); -webkit-background-clip: text; -webkit-text-fill-color: transparent; font-size: 24px;">🔐 FURI WEB</h1>
                    <p style="color: #8888aa;">Xác minh đặt lại mật khẩu</p>
                </div>
                <p>Xin chào <strong>${username}</strong>,</p>
                <p>Bạn đã yêu cầu đặt lại mật khẩu. Vui lòng sử dụng mã xác minh dưới đây:</p>
                <div style="background: #0a0a0f; border: 2px solid #ff1744; border-radius: 12px; padding: 20px; text-align: center; margin: 20px 0;">
                    <div style="font-size: 32px; font-weight: 800; color: #ff1744; letter-spacing: 8px;">${otpCode}</div>
                </div>
                <p style="color: #8888aa; text-align: center;">
                    ⏰ Mã có hiệu lực trong <strong style="color: #00e5ff;">5 phút</strong><br>
                    🔒 Không chia sẻ mã này với bất kỳ ai
                </p>
                <div style="text-align: center; color: #555577; font-size: 12px; margin-top: 20px; border-top: 1px solid #2a2a3a; padding-top: 15px;">
                    <p>© 2024 FURI WEB — Mod Store</p>
                </div>
            </div>
        </body>
        </html>
        `;

        await transporter.sendMail({
            from: `"FURI WEB" <${config.email.user}>`,
            to: toEmail,
            subject: '[FURI WEB] Mã xác minh đặt lại mật khẩu',
            html,
        });

        return true;
    } catch (error) {
        console.error('Lỗi gửi email:', error);
        return false;
    }
};

module.exports = {
    sendEmailOTP,
};
