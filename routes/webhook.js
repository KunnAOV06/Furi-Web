const express = require('express');
const router = express.Router();
const config = require('../config');
const { sendTelegramNotification } = require('../utils/telegram');
const { formatPrice } = require('../utils/helpers');

const User = require('../models/User');
const DepositRequest = require('../models/DepositRequest');
const Transaction = require('../models/Transaction');

// SePay Webhook
router.post('/sepay', async (req, res) => {
    try {
        const data = req.body;
        console.log('📥 Webhook nhận:', JSON.stringify(data, null, 2));

        const transaction = data.transaction || {};
        const amount = transaction.amount || 0;
        const content = (transaction.content || '').trim();
        const bankAccount = transaction.bank_account || '';
        const bankName = transaction.bank_name || '';
        const status = transaction.status || '';

        // Chỉ xử lý giao dịch thành công
        if (status && status.toLowerCase() !== 'success') {
            return res.json({ status: 'success', message: 'Transaction not completed' });
        }

        // Kiểm tra số tài khoản nhận
        if (bankAccount && bankAccount !== config.bankConfig.accountNumber) {
            console.log(`⚠️ Số tài khoản không khớp: ${bankAccount} != ${config.bankConfig.accountNumber}`);
            return res.json({ status: 'error', message: 'Bank account mismatch' });
        }

        console.log(`💰 Giao dịch: ${formatPrice(amount)} - Nội dung: ${content}`);

        // Tìm giao dịch nạp tiền
        let deposit = null;

        // Cách 1: Tìm theo transaction_code
        deposit = await DepositRequest.findByCode(content);

        // Cách 2: Tìm theo deposit_code trong nội dung
        if (!deposit) {
            const users = await User.getAll();
            for (const user of users) {
                if (user.deposit_code && content.includes(user.deposit_code)) {
                    const deposits = await DepositRequest.findByUser(user.id);
                    deposit = deposits.find(d => d.status === 'pending');
                    if (deposit) break;
                }
            }
        }

        if (!deposit) {
            console.log(`❌ Không tìm thấy giao dịch cho content: ${content}`);
            return res.json({ 
                status: 'error', 
                message: 'Transaction not found',
                content,
                amount 
            });
        }

        // Kiểm tra đã xử lý chưa
        if (deposit.status === 'completed') {
            return res.json({ status: 'success', message: 'Already processed' });
        }

        // Xác nhận nạp tiền
        await DepositRequest.updateStatus(deposit.id, 'completed', `SePay webhook - Ref: ${transaction.transaction_id || ''}`);
        await User.updateBalance(deposit.user_id, deposit.amount);

        await Transaction.create({
            user_id: deposit.user_id,
            amount: deposit.amount,
            type: 'deposit',
            description: `Nạp tiền tự động qua SePay - ${deposit.transaction_code}`,
        });

        const user = await User.findById(deposit.user_id);
        console.log(`✅ Đã xác nhận nạp ${formatPrice(deposit.amount)} cho user ${user.username}`);

        // Telegram notification
        await sendTelegramNotification(
            '💰 NẠP TIỀN THÀNH CÔNG (Auto)',
            `👤 ${user.username}\n💰 ${formatPrice(deposit.amount)}\n🆔 ${deposit.transaction_code}\n🤖 Xác nhận tự động qua SePay`,
            'success'
        );

        res.json({
            status: 'success',
            message: 'Deposit confirmed successfully',
            deposit_id: deposit.id,
            user: user.username,
            amount: formatPrice(deposit.amount),
        });

    } catch (error) {
        console.error('❌ Lỗi webhook SePay:', error);
        res.status(500).json({ status: 'error', message: error.message });
    }
});

// Webhook test endpoint
router.get('/sepay/test', (req, res) => {
    res.json({
        status: 'success',
        message: 'Webhook endpoint is working',
        time: new Date().toISOString(),
    });
});

module.exports = router;