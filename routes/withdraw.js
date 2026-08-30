const express = require('express');
const router = express.Router();
const { isAuthenticated } = require('../middleware/auth');
const { sendTelegramNotification } = require('../utils/telegram');
const { formatPrice } = require('../utils/helpers');
const config = require('../config');

const User = require('../models/User');
const WithdrawRequest = require('../models/WithdrawRequest');
const Transaction = require('../models/Transaction');

router.get('/', isAuthenticated, async (req, res) => {
    try {
        if (!req.user.is_seller && !req.user.is_admin) {
            req.flash('error', 'Chỉ người bán hàng mới được rút tiền');
            return res.redirect('/profile');
        }
        
        const user = await User.findById(req.user.id);
        const fee = user.withdraw_count < config.freeWithdrawLimit ? 0 : config.withdrawFee;
        const withdrawals = await WithdrawRequest.findByUser(user.id);
        
        res.render('withdraw', {
            title: 'Rút tiền',
            fee,
            minWithdraw: config.minWithdraw,
            freeLimit: config.freeWithdrawLimit,
            withdrawals,
            user,
        });
    } catch (error) {
        console.error(error);
        res.redirect('/');
    }
});

router.post('/', isAuthenticated, async (req, res) => {
    try {
        const { amount, bank_name, bank_account_name, bank_account_number } = req.body;
        const amountNum = parseFloat(amount);
        const user = await User.findById(req.user.id);
        
        if (amountNum < config.minWithdraw) {
            req.flash('error', `Số tiền rút tối thiểu là ${formatPrice(config.minWithdraw)}`);
            return res.redirect('/withdraw');
        }
        if (amountNum > user.balance) {
            req.flash('error', 'Số dư không đủ để rút');
            return res.redirect('/withdraw');
        }
        
        const fee = user.withdraw_count < config.freeWithdrawLimit ? 0 : config.withdrawFee;
        const netAmount = amountNum - fee;
        
        if (netAmount <= 0) {
            req.flash('error', 'Số tiền sau phí không hợp lệ');
            return res.redirect('/withdraw');
        }
        
        // Tạo yêu cầu rút
        const withdraw = await WithdrawRequest.create({
            user_id: user.id,
            amount: amountNum,
            fee,
            net_amount: netAmount,
            bank_name,
            bank_account_name,
            bank_account_number,
        });
        
        // Cập nhật balance và withdraw_count
        await User.updateBalance(user.id, -amountNum);
        await User.update(user.id, { withdraw_count: user.withdraw_count + 1 });
        
        await Transaction.create({
            user_id: user.id,
            amount: -amountNum,
            type: 'withdraw',
            description: `Yêu cầu rút tiền #${withdraw.id}`,
        });
        
        await sendTelegramNotification(
            '💸 YÊU CẦU RÚT TIỀN MỚI',
            `👤 ${user.username}\n🆔 #${withdraw.id}\n💰 ${formatPrice(amountNum)}\n💸 Phí: ${formatPrice(fee)}\n🏦 ${bank_name}\n🔢 ${bank_account_number}`,
            'warning'
        );
        
        req.flash('success', 'Yêu cầu rút tiền đã được gửi! Bạn sẽ nhận được tiền trong vòng 24h.');
        res.redirect('/withdraw/history');
    } catch (error) {
        console.error(error);
        req.flash('error', 'Rút tiền thất bại');
        res.redirect('/withdraw');
    }
});

router.get('/history', isAuthenticated, async (req, res) => {
    try {
        const withdrawals = await WithdrawRequest.findByUser(req.user.id);
        res.render('withdraw_history', {
            title: 'Lịch sử rút tiền',
            withdrawals,
        });
    } catch (error) {
        console.error(error);
        res.redirect('/');
    }
});

module.exports = router;