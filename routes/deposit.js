const express = require('express');
const router = express.Router();
const { isAuthenticated } = require('../middleware/auth');
const DepositRequest = require('../models/DepositRequest');
const { generateCode, generateVietQR, formatPrice } = require('../utils/helpers');
const { sendTelegramNotification } = require('../utils/telegram');
const config = require('../config');

router.get('/', isAuthenticated, async (req, res) => {
    try {
        const deposits = await DepositRequest.findByUser(req.user.id);
        res.render('deposit_form', {
            title: 'Nạp tiền',
            deposits,
            bank: config.bankConfig,
        });
    } catch (error) {
        res.redirect('/');
    }
});

router.post('/create', isAuthenticated, async (req, res) => {
    try {
        const amount = parseFloat(req.body.amount);
        if (amount < 10000) {
            req.flash('error', 'Số tiền nạp tối thiểu là 10,000đ');
            return res.redirect('/deposit');
        }
        
        const transactionCode = `${req.user.deposit_code}_${generateCode('', 6)}`;
        const deposit = await DepositRequest.create({
            user_id: req.user.id,
            amount,
            transaction_code: transactionCode,
        });
        
        await sendTelegramNotification(
            'YÊU CẦU NẠP TIỀN MỚI',
            `👤 ${req.user.username}\n💰 ${formatPrice(amount)}\n🆔 ${transactionCode}`,
            'info'
        );
        
        const qrUrl = generateVietQR(
            config.bankConfig.accountNumber,
            config.bankConfig.accountName,
            config.bankConfig.bankId,
            amount,
            transactionCode
        );
        
        res.render('deposit_qr', {
            title: 'Nạp tiền - QR',
            deposit,
            bank: config.bankConfig,
            amount,
            description: transactionCode,
            qrUrl,
        });
    } catch (error) {
        console.error(error);
        req.flash('error', 'Tạo yêu cầu nạp tiền thất bại');
        res.redirect('/deposit');
    }
});

router.post('/confirm/:id', isAuthenticated, async (req, res) => {
    try {
        const deposit = await DepositRequest.findById(req.params.id);
        if (!deposit || deposit.user_id !== req.user.id) {
            req.flash('error', 'Không có quyền thực hiện');
            return res.redirect('/deposit');
        }
        if (deposit.status !== 'pending') {
            req.flash('error', 'Yêu cầu đã được xử lý');
            return res.redirect('/deposit');
        }
        
        await DepositRequest.updateStatus(deposit.id, 'confirmed', 'Người dùng xác nhận chuyển khoản');
        await sendTelegramNotification(
            '✅ XÁC NHẬN CHUYỂN KHOẢN',
            `👤 ${req.user.username}\n💰 ${formatPrice(deposit.amount)}\n🆔 ${deposit.transaction_code}`,
            'success'
        );
        
        req.flash('success', '✅ Xác nhận thành công! Admin sẽ kiểm tra và xác nhận.');
        res.redirect('/deposit');
    } catch (error) {
        console.error(error);
        req.flash('error', 'Xác nhận thất bại');
        res.redirect('/deposit');
    }
});

router.get('/check/:id', isAuthenticated, async (req, res) => {
    try {
        const deposit = await DepositRequest.findById(req.params.id);
        if (!deposit || (deposit.user_id !== req.user.id && !req.user.is_admin)) {
            return res.status(403).json({ error: 'Unauthorized' });
        }
        res.json({ status: deposit.status, amount: deposit.amount });
    } catch (error) {
        res.status(500).json({ error: 'Lỗi server' });
    }
});

module.exports = router;