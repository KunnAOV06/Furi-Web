const express = require('express');
const router = express.Router();
const crypto = require('crypto');
const config = require('../config');
const { isAuthenticated } = require('../middleware/auth');
const { sendTelegramNotification } = require('../utils/telegram');
const { formatPrice, calculateCommission } = require('../utils/helpers');

const User = require('../models/User');
const FileItem = require('../models/FileItem');
const Purchase = require('../models/Purchase');
const Transaction = require('../models/Transaction');
const DiscountCode = require('../models/DiscountCode');
const GlobalSale = require('../models/GlobalSale');
const ProductSale = require('../models/ProductSale');
const NewUserDiscount = require('../models/NewUserDiscount');

// Buy file
router.post('/buy/:id', isAuthenticated, async (req, res) => {
    try {
        const file = await FileItem.findById(req.params.id);
        if (!file || !file.is_active) {
            req.flash('error', 'Sản phẩm không tồn tại');
            return res.redirect('/');
        }
        
        const user = await User.findById(req.user.id);
        let price = file.price;
        let discountPercent = 0;
        const discountCode = req.body.discount_code;
        
        // Kiểm tra sale
        // ... logic sale
        
        // Kiểm tra mã giảm giá
        if (discountCode) {
            const discount = await DiscountCode.findByCode(discountCode);
            if (discount && new Date() < new Date(discount.valid_until) && discount.used_count < discount.max_uses) {
                discountPercent = discount.discount_percent;
                price = price * (1 - discountPercent / 100);
                await DiscountCode.use(discountCode);
            }
        }
        
        // Kiểm tra FREE
        if (discountCode && discountCode.toUpperCase() === 'FREE100' && file.free_link) {
            req.flash('success', '🎁 Bạn đã nhận Free sản phẩm!');
            return res.redirect(`/file/${file.id}`);
        }
        
        if (user.balance < price) {
            req.flash('error', `Số dư không đủ. Vui lòng nạp tiền.`);
            return res.redirect(`/file/${file.id}`);
        }
        
        const commission = calculateCommission(price);
        const downloadToken = crypto.randomBytes(32).toString('hex');
        
        // Cập nhật balance
        await User.updateBalance(user.id, -price);
        await User.updateBalance(file.uploaded_by, commission.seller);
        await User.update(file.uploaded_by, { 
            total_sales: (await User.findById(file.uploaded_by)).total_sales + commission.seller 
        });
        
        // Tạo purchase
        const purchase = await Purchase.create({
            user_id: user.id,
            file_id: file.id,
            amount_paid: price,
            seller_earned: commission.seller,
            admin_earned: commission.admin,
            discount_applied: discountPercent,
        });
        
        // Tạo transaction
        await Transaction.create({
            user_id: user.id,
            amount: -price,
            type: 'purchase',
            description: `Mua ${file.product_name}`,
        });
        await Transaction.create({
            user_id: file.uploaded_by,
            amount: commission.seller,
            type: 'sale',
            description: `Bán file: ${file.product_name}`,
        });
        
        // Telegram notification
        await sendTelegramNotification(
            '🛒 ĐƠN HÀNG MỚI',
            `👤 ${user.username}\n💰 ${formatPrice(price)}\n📦 ${file.product_name}`,
            'info'
        );
        
        req.flash('success', `Mua thành công! Bạn đã trả ${formatPrice(price)}`);
        res.redirect('/purchase/history');
    } catch (error) {
        console.error(error);
        req.flash('error', 'Mua hàng thất bại');
        res.redirect(`/file/${req.params.id}`);
    }
});

// Purchase history
router.get('/history', isAuthenticated, async (req, res) => {
    try {
        const purchases = await Purchase.findByUser(req.user.id);
        const totalSpent = purchases.reduce((sum, p) => sum + p.amount_paid, 0);
        res.render('purchase_history', {
            title: 'Lịch sử mua hàng',
            purchases,
            totalSpent,
        });
    } catch (error) {
        console.error(error);
        res.redirect('/');
    }
});

// Download with token
router.get('/download/:token', isAuthenticated, async (req, res) => {
    try {
        const purchase = await Purchase.findByToken(req.params.token);
        if (!purchase || purchase.user_id !== req.user.id) {
            req.flash('error', 'Link tải không hợp lệ');
            return res.redirect('/purchase/history');
        }
        
        const file = await FileItem.findById(purchase.file_id);
        if (!file || !file.is_active) {
            req.flash('error', 'File không tồn tại hoặc đã bị xóa');
            return res.redirect('/purchase/history');
        }
        
        await FileItem.incrementDownload(file.id);
        res.redirect(`/file/download/${file.id}`);
    } catch (error) {
        console.error(error);
        req.flash('error', 'Đã xảy ra lỗi');
        res.redirect('/purchase/history');
    }
});

module.exports = router;