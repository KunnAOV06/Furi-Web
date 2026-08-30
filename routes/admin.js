const express = require('express');
const router = express.Router();
const { isAuthenticated, isAdmin } = require('../middleware/auth');

// Import models
const User = require('../models/User');
const FileItem = require('../models/FileItem');
const Purchase = require('../models/Purchase');
const DepositRequest = require('../models/DepositRequest');
const WithdrawRequest = require('../models/WithdrawRequest');
const DiscountCode = require('../models/DiscountCode');
const Transaction = require('../models/Transaction');
const SiteSettings = require('../models/SiteSettings');
const GlobalSale = require('../models/GlobalSale');
const ProductSale = require('../models/ProductSale');

// Dashboard
router.get('/dashboard', isAuthenticated, isAdmin, async (req, res) => {
    try {
        const users = await User.getAll();
        const files = await FileItem.getAll();
        const purchases = await Purchase.getAll();
        const recentPurchases = await Purchase.getRecent(10);
        const pendingDeposits = await DepositRequest.getAllPending();
        const pendingWithdraws = await WithdrawRequest.getAllPending();
        
        const totalRevenue = purchases.reduce((sum, p) => sum + p.admin_earned, 0);
        const totalDownloads = files.reduce((sum, f) => sum + f.download_count, 0);
        
        res.render('admin_dashboard', {
            title: 'Bảng điều khiển',
            users,
            files,
            purchases,
            recentPurchases,
            pendingDeposits: pendingDeposits.length,
            pendingWithdraws: pendingWithdraws.length,
            totalRevenue,
            totalUsers: users.length,
            totalFiles: files.length,
            totalDownloads,
        });
    } catch (error) {
        console.error(error);
        res.redirect('/');
    }
});

// Users management
router.get('/users', isAuthenticated, isAdmin, async (req, res) => {
    try {
        const users = await User.getAll();
        res.render('admin_users', { title: 'Quản lý người dùng', users });
    } catch (error) {
        res.redirect('/admin/dashboard');
    }
});

router.post('/users/:id/balance', isAuthenticated, isAdmin, async (req, res) => {
    try {
        const { amount } = req.body;
        await User.updateBalance(req.params.id, parseFloat(amount));
        await Transaction.create({
            user_id: req.params.id,
            amount: parseFloat(amount),
            type: 'deposit',
            description: 'Admin cộng tiền',
        });
        req.flash('success', 'Đã cộng tiền thành công');
        res.redirect('/admin/users');
    } catch (error) {
        req.flash('error', 'Cộng tiền thất bại');
        res.redirect('/admin/users');
    }
});

router.post('/users/:id/seller', isAuthenticated, isAdmin, async (req, res) => {
    try {
        const user = await User.findById(req.params.id);
        await User.update(user.id, { is_seller: user.is_seller ? 0 : 1 });
        req.flash('success', `Đã ${user.is_seller ? 'thu hồi' : 'cấp'} quyền bán hàng`);
        res.redirect('/admin/users');
    } catch (error) {
        req.flash('error', 'Thất bại');
        res.redirect('/admin/users');
    }
});

router.post('/users/:id/admin', isAuthenticated, isAdmin, async (req, res) => {
    try {
        const user = await User.findById(req.params.id);
        const newAdminStatus = user.is_admin ? 0 : 1;
        await User.update(user.id, { 
            is_admin: newAdminStatus,
            is_seller: newAdminStatus ? 1 : user.is_seller,
        });
        req.flash('success', `Đã ${user.is_admin ? 'thu hồi' : 'cấp'} quyền Admin`);
        res.redirect('/admin/users');
    } catch (error) {
        req.flash('error', 'Thất bại');
        res.redirect('/admin/users');
    }
});

// Files management
router.get('/files', isAuthenticated, isAdmin, async (req, res) => {
    try {
        const files = await FileItem.getAll();
        res.render('admin_files', { title: 'Quản lý sản phẩm', files });
    } catch (error) {
        res.redirect('/admin/dashboard');
    }
});

router.post('/files/:id/toggle', isAuthenticated, isAdmin, async (req, res) => {
    try {
        await FileItem.toggleActive(req.params.id);
        req.flash('success', 'Đã cập nhật trạng thái');
        res.redirect('/admin/files');
    } catch (error) {
        req.flash('error', 'Thất bại');
        res.redirect('/admin/files');
    }
});

router.post('/files/:id/delete', isAuthenticated, isAdmin, async (req, res) => {
    try {
        await FileItem.delete(req.params.id);
        req.flash('success', 'Đã xóa sản phẩm');
        res.redirect('/admin/files');
    } catch (error) {
        req.flash('error', 'Xóa thất bại');
        res.redirect('/admin/files');
    }
});

// Deposits management
router.get('/deposits', isAuthenticated, isAdmin, async (req, res) => {
    try {
        const deposits = await DepositRequest.getAll();
        res.render('admin_deposits', { title: 'Quản lý nạp tiền', deposits });
    } catch (error) {
        res.redirect('/admin/dashboard');
    }
});

router.post('/deposits/:id/confirm', isAuthenticated, isAdmin, async (req, res) => {
    try {
        const deposit = await DepositRequest.findById(req.params.id);
        if (deposit.status === 'pending' || deposit.status === 'confirmed') {
            await DepositRequest.updateStatus(deposit.id, 'completed');
            await User.updateBalance(deposit.user_id, deposit.amount);
            await Transaction.create({
                user_id: deposit.user_id,
                amount: deposit.amount,
                type: 'deposit',
                description: `Nạp tiền - Mã ${deposit.transaction_code}`,
            });
            const user = await User.findById(deposit.user_id);
            req.flash('success', `Đã xác nhận nạp ${formatPrice(deposit.amount)} cho ${user.username}`);
        }
        res.redirect('/admin/deposits');
    } catch (error) {
        req.flash('error', 'Xác nhận thất bại');
        res.redirect('/admin/deposits');
    }
});

router.post('/deposits/:id/cancel', isAuthenticated, isAdmin, async (req, res) => {
    try {
        const deposit = await DepositRequest.findById(req.params.id);
        if (deposit.status === 'pending') {
            await DepositRequest.updateStatus(deposit.id, 'cancelled', 'Admin hủy');
            req.flash('success', 'Đã hủy yêu cầu nạp tiền');
        }
        res.redirect('/admin/deposits');
    } catch (error) {
        req.flash('error', 'Hủy thất bại');
        res.redirect('/admin/deposits');
    }
});

// Withdraws management
router.get('/withdraws', isAuthenticated, isAdmin, async (req, res) => {
    try {
        const withdraws = await WithdrawRequest.getAll();
        res.render('admin_withdraws', { title: 'Quản lý rút tiền', withdraws });
    } catch (error) {
        res.redirect('/admin/dashboard');
    }
});

router.post('/withdraws/:id/process', isAuthenticated, isAdmin, async (req, res) => {
    try {
        await WithdrawRequest.updateStatus(req.params.id, 'processing');
        req.flash('success', 'Đã chuyển sang xử lý');
        res.redirect('/admin/withdraws');
    } catch (error) {
        req.flash('error', 'Thất bại');
        res.redirect('/admin/withdraws');
    }
});

router.post('/withdraws/:id/complete', isAuthenticated, isAdmin, async (req, res) => {
    try {
        await WithdrawRequest.updateStatus(req.params.id, 'completed');
        req.flash('success', 'Đã hoàn tất rút tiền');
        res.redirect('/admin/withdraws');
    } catch (error) {
        req.flash('error', 'Thất bại');
        res.redirect('/admin/withdraws');
    }
});

router.post('/withdraws/:id/reject', isAuthenticated, isAdmin, async (req, res) => {
    try {
        const withdraw = await WithdrawRequest.findById(req.params.id);
        if (withdraw.status === 'pending') {
            await WithdrawRequest.updateStatus(withdraw.id, 'rejected');
            await User.updateBalance(withdraw.user_id, withdraw.amount);
            await Transaction.create({
                user_id: withdraw.user_id,
                amount: withdraw.amount,
                type: 'refund',
                description: `Hoàn tiền rút #${withdraw.id} do từ chối`,
            });
            req.flash('success', 'Đã từ chối và hoàn tiền');
        }
        res.redirect('/admin/withdraws');
    } catch (error) {
        req.flash('error', 'Thất bại');
        res.redirect('/admin/withdraws');
    }
});

// Discount codes
router.get('/discounts', isAuthenticated, isAdmin, async (req, res) => {
    try {
        const discounts = await DiscountCode.getAll();
        res.render('admin_discounts', { title: 'Mã giảm giá', discounts });
    } catch (error) {
        res.redirect('/admin/dashboard');
    }
});

router.post('/discounts/add', isAuthenticated, isAdmin, async (req, res) => {
    try {
        const { code, percent, days_valid, max_uses } = req.body;
        const validUntil = new Date();
        validUntil.setDate(validUntil.getDate() + parseInt(days_valid));
        await DiscountCode.create({
            code,
            discount_percent: parseFloat(percent),
            valid_until: validUntil.toISOString(),
            max_uses: parseInt(max_uses) || 1,
        });
        req.flash('success', 'Thêm mã giảm giá thành công');
        res.redirect('/admin/discounts');
    } catch (error) {
        req.flash('error', 'Thêm thất bại');
        res.redirect('/admin/discounts');
    }
});

router.post('/discounts/:id/delete', isAuthenticated, isAdmin, async (req, res) => {
    try {
        await DiscountCode.delete(req.params.id);
        req.flash('success', 'Đã xóa mã giảm giá');
        res.redirect('/admin/discounts');
    } catch (error) {
        req.flash('error', 'Xóa thất bại');
        res.redirect('/admin/discounts');
    }
});

// Sale settings
router.get('/sale-settings', isAuthenticated, isAdmin, async (req, res) => {
    try {
        const globalSale = await GlobalSale.get();
        const productSales = await ProductSale.getAll();
        const files = await FileItem.getAll();
        res.render('admin_sale_settings', {
            title: 'Quản lý khuyến mãi',
            globalSale,
            productSales,
            files,
        });
    } catch (error) {
        res.redirect('/admin/dashboard');
    }
});

router.post('/sale-settings', isAuthenticated, isAdmin, async (req, res) => {
    try {
        const { global_sale, global_discount, sale_days } = req.body;
        await GlobalSale.update({
            is_active: !!global_sale,
            discount_percent: parseFloat(global_discount) || 0,
            start_date: new Date().toISOString(),
            end_date: new Date(Date.now() + parseInt(sale_days || 7) * 24 * 60 * 60 * 1000).toISOString(),
        });
        req.flash('success', 'Đã cập nhật sale toàn bộ');
        res.redirect('/admin/sale-settings');
    } catch (error) {
        req.flash('error', 'Cập nhật thất bại');
        res.redirect('/admin/sale-settings');
    }
});

router.post('/product-sale/:id', isAuthenticated, isAdmin, async (req, res) => {
    try {
        const { discount, days } = req.body;
        await ProductSale.set(req.params.id, {
            discount_percent: parseFloat(discount) || 0,
            is_active: parseFloat(discount) > 0,
            start_date: new Date().toISOString(),
            end_date: new Date(Date.now() + parseInt(days || 0) * 24 * 60 * 60 * 1000).toISOString(),
        });
        req.flash('success', 'Đã cập nhật sale cho sản phẩm');
        res.redirect('/admin/sale-settings');
    } catch (error) {
        req.flash('error', 'Cập nhật thất bại');
        res.redirect('/admin/sale-settings');
    }
});

// Welcome banner
router.post('/welcome-banner', isAuthenticated, isAdmin, async (req, res) => {
    try {
        await SiteSettings.set('welcome_banner', req.body.content);
        req.flash('success', 'Đã cập nhật thông báo chào mừng');
        res.redirect('/admin/dashboard');
    } catch (error) {
        req.flash('error', 'Cập nhật thất bại');
        res.redirect('/admin/dashboard');
    }
});

module.exports = router;