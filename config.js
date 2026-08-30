const dotenv = require('dotenv');
dotenv.config();

module.exports = {
    port: process.env.PORT || 5000,
    nodeEnv: process.env.NODE_ENV || 'development',
    secretKey: process.env.SECRET_KEY || 'your-secret-key',
    
    // Database
    databaseUrl: process.env.DATABASE_URL || 'sqlite:./datafuri.db',
    
    // Telegram
    telegramToken: process.env.TELEGRAM_TOKEN || '',
    telegramChatId: process.env.TELEGRAM_CHAT_ID || '',
    
    // SePay
    sepayApiKey: process.env.SEPAY_API_KEY || '',
    
    // Email
    email: {
        host: process.env.EMAIL_HOST || 'smtp.gmail.com',
        port: parseInt(process.env.EMAIL_PORT) || 587,
        user: process.env.EMAIL_USER || '',
        pass: process.env.EMAIL_PASS || '',
    },
    
    // Cloudinary
    cloudinary: {
        cloudName: process.env.CLOUDINARY_CLOUD_NAME || 'kvm7dgqo',
        apiKey: process.env.CLOUDINARY_API_KEY || '832773425244141',
        apiSecret: process.env.CLOUDINARY_API_SECRET || 'P8NZsf50ECSnqDd9tYyVA1KQ-0A',
    },
    
    // Bank
    bankConfig: {
        bankId: 'TCB',
        bankName: 'Techcombank',
        accountName: 'LE BA NAM',
        accountNumber: '8842006666',
    },
    
    // Commission
    commissionRate: 0.8,
    minWithdraw: 10000,
    withdrawFee: 2500,
    freeWithdrawLimit: 5,
    
    // Upload
    uploadFolder: 'uploads',
    demoFolder: 'uploads/demo_files',
    thumbnailFolder: 'uploads/thumbnails',
    maxFileSize: 50 * 1024 * 1024,
    allowedExtensions: ['png', 'jpg', 'jpeg', 'gif', 'webp'],
    
    // Timezone
    timezone: 'Asia/Ho_Chi_Minh',
};