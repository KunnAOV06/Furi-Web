const express = require('express');
const router = express.Router();
const bcrypt = require('bcryptjs');
const crypto = require('crypto');
const User = require('../models/User');
const OTPVerification = require('../models/OTPVerification');
const Transaction = require('../models/Transaction');
const { sendEmailOTP } = require('../utils/email');
const { generateOTP, generateCode } = require('../utils/helpers');
const { isAuthenticated } = require('../middleware/auth');

// Register
router.get('/register', (req, res) => {
    if (req.user) return res.redirect('/');
    res.render('register', { title: 'Đăng ký' });
});

router.post('/register', async (req, res) => {
    try {
        const { username, email, password, referral_code } = req.body;
        
        const existingUser = await User.findByUsername(username);
        if (existingUser) {
            req.flash('error', 'Tên đăng nhập đã tồn tại');
            return res.redirect('/auth/register');
        }
        
        const existingEmail = await User.findByEmail(email);
        if (existingEmail) {
            req.flash('error', 'Email đã được đăng ký');
            return res.redirect('/auth/register');
        }
        
        const user = await User.create({ username, email, password, referral_code });
        
        // Tạo mã giảm giá thành viên mới
        const discountCode = `NEW15${user.id}${generateCode('', 4)}`;
        // Lưu vào NewUserDiscount (sẽ implement sau)
        
        req.flash('success', `🎉 Chào mừng bạn! Mã giảm giá 15%: ${discountCode}`);
        req.flash('success', 'Đăng ký thành công! Vui lòng đăng nhập.');
        res.redirect('/auth/login');
    } catch (error) {
        console.error(error);
        req.flash('error', 'Đăng ký thất bại, vui lòng thử lại');
        res.redirect('/auth/register');
    }
});

// Login
router.get('/login', (req, res) => {
    if (req.user) return res.redirect('/');
    res.render('login', { title: 'Đăng nhập' });
});

router.post('/login', async (req, res) => {
    try {
        const { username, password } = req.body;
        const user = await User.findByUsername(username);
        
        if (!user || !bcrypt.compareSync(password, user.password_hash)) {
            req.flash('error', 'Tên đăng nhập hoặc mật khẩu không đúng');
            return res.redirect('/auth/login');
        }
        
        req.session.userId = user.id;
        req.flash('success', `Chào mừng ${user.username} trở lại!`);
        const next = req.query.next || '/';
        res.redirect(next);
    } catch (error) {
        console.error(error);
        req.flash('error', 'Đăng nhập thất bại');
        res.redirect('/auth/login');
    }
});

// Logout
router.get('/logout', (req, res) => {
    req.session.destroy();
    res.redirect('/');
});

// Forgot Password
router.get('/forgot-password', (req, res) => {
    res.render('forgot_password', { title: 'Quên mật khẩu' });
});

router.post('/forgot-password', async (req, res) => {
    try {
        const { email } = req.body;
        const user = await User.findByEmail(email);
        if (!user) {
            req.flash('error', 'Email không tồn tại trong hệ thống');
            return res.redirect('/auth/forgot-password');
        }
        
        const otpCode = generateOTP();
        const expiresAt = new Date(Date.now() + 5 * 60 * 1000); // 5 phút
        
        await OTPVerification.create({ email, otp_code: otpCode, expires_at: expiresAt.toISOString() });
        
        if (await sendEmailOTP(email, otpCode, user.username)) {
            req.flash('success', `✅ Mã xác minh đã được gửi đến ${email}. Có hiệu lực 5 phút.`);
            req.session.resetEmail = email;
            res.redirect('/auth/verify-otp');
        } else {
            req.flash('error', '❌ Không thể gửi email. Vui lòng thử lại sau.');
            res.redirect('/auth/forgot-password');
        }
    } catch (error) {
        console.error(error);
        req.flash('error', 'Đã xảy ra lỗi');
        res.redirect('/auth/forgot-password');
    }
});

// Verify OTP
router.get('/verify-otp', (req, res) => {
    const email = req.session.resetEmail;
    if (!email) {
        req.flash('error', 'Vui lòng nhập email trước');
        return res.redirect('/auth/forgot-password');
    }
    res.render('verify_otp', { title: 'Xác minh OTP', email });
});

router.post('/verify-otp', async (req, res) => {
    try {
        const email = req.session.resetEmail;
        if (!email) {
            req.flash('error', 'Vui lòng nhập email trước');
            return res.redirect('/auth/forgot-password');
        }
        
        const { otp_code } = req.body;
        const otp = await OTPVerification.findByEmailAndCode(email, otp_code);
        
        if (!otp) {
            req.flash('error', '❌ Mã xác minh không hợp lệ hoặc đã hết hạn');
            return res.redirect('/auth/verify-otp');
        }
        
        await OTPVerification.markUsed(otp.id);
        req.session.resetVerified = true;
        req.flash('success', '✅ Xác minh thành công! Vui lòng đặt lại mật khẩu.');
        res.redirect('/auth/reset-password');
    } catch (error) {
        console.error(error);
        req.flash('error', 'Đã xảy ra lỗi');
        res.redirect('/auth/verify-otp');
    }
});

// Reset Password
router.get('/reset-password', (req, res) => {
    if (!req.session.resetVerified) {
        req.flash('error', 'Vui lòng xác minh OTP trước');
        return res.redirect('/auth/verify-otp');
    }
    const email = req.session.resetEmail;
    if (!email) {
        req.flash('error', 'Vui lòng nhập email trước');
        return res.redirect('/auth/forgot-password');
    }
    res.render('reset_password', { title: 'Đặt lại mật khẩu', email });
});

router.post('/reset-password', async (req, res) => {
    try {
        if (!req.session.resetVerified) {
            req.flash('error', 'Vui lòng xác minh OTP trước');
            return res.redirect('/auth/verify-otp');
        }
        
        const email = req.session.resetEmail;
        if (!email) {
            req.flash('error', 'Vui lòng nhập email trước');
            return res.redirect('/auth/forgot-password');
        }
        
        const { password, confirm_password } = req.body;
        if (password.length < 6) {
            req.flash('error', 'Mật khẩu phải có ít nhất 6 ký tự');
            return res.redirect('/auth/reset-password');
        }
        if (password !== confirm_password) {
            req.flash('error', 'Mật khẩu xác nhận không khớp');
            return res.redirect('/auth/reset-password');
        }
        
        const user = await User.findByEmail(email);
        if (!user) {
            req.flash('error', 'Người dùng không tồn tại');
            return res.redirect('/auth/forgot-password');
        }
        
        const salt = bcrypt.genSaltSync(10);
        const passwordHash = bcrypt.hashSync(password, salt);
        await User.update(user.id, { password_hash: passwordHash });
        
        delete req.session.resetEmail;
        delete req.session.resetVerified;
        
        req.flash('success', '✅ Đặt lại mật khẩu thành công! Vui lòng đăng nhập.');
        res.redirect('/auth/login');
    } catch (error) {
        console.error(error);
        req.flash('error', 'Đã xảy ra lỗi');
        res.redirect('/auth/reset-password');
    }
});

// Resend OTP
router.post('/resend-otp', async (req, res) => {
    try {
        const email = req.session.resetEmail;
        if (!email) {
            return res.json({ success: false, message: 'Không tìm thấy email' });
        }
        
        const user = await User.findByEmail(email);
        if (!user) {
            return res.json({ success: false, message: 'Email không tồn tại' });
        }
        
        const otpCode = generateOTP();
        const expiresAt = new Date(Date.now() + 5 * 60 * 1000);
        await OTPVerification.create({ email, otp_code: otpCode, expires_at: expiresAt.toISOString() });
        
        if (await sendEmailOTP(email, otpCode, user.username)) {
            res.json({ success: true, message: 'Đã gửi lại mã OTP' });
        } else {
            res.json({ success: false, message: 'Không thể gửi email' });
        }
    } catch (error) {
        res.json({ success: false, message: 'Lỗi hệ thống' });
    }
});

// Profile
router.get('/profile', isAuthenticated, async (req, res) => {
    try {
        const user = await User.findById(req.user.id);
        const purchases = await require('../models/Purchase').findByUser(user.id);
        const totalSpent = purchases.reduce((sum, p) => sum + p.amount_paid, 0);
        const totalEarned = 0; // Tính từ sales
        
        res.render('profile', {
            title: 'Hồ sơ',
            user,
            totalSpent,
            totalEarned,
        });
    } catch (error) {
        console.error(error);
        res.redirect('/');
    }
});

// Change Password
router.get('/change-password', isAuthenticated, (req, res) => {
    res.render('change_password', { title: 'Đổi mật khẩu' });
});

router.post('/change-password', isAuthenticated, async (req, res) => {
    try {
        const { current_password, new_password, confirm_password } = req.body;
        const user = await User.findById(req.user.id);
        
        if (!bcrypt.compareSync(current_password, user.password_hash)) {
            req.flash('error', 'Mật khẩu hiện tại không đúng');
            return res.redirect('/auth/change-password');
        }
        if (new_password.length < 6) {
            req.flash('error', 'Mật khẩu mới phải có ít nhất 6 ký tự');
            return res.redirect('/auth/change-password');
        }
        if (new_password !== confirm_password) {
            req.flash('error', 'Mật khẩu xác nhận không khớp');
            return res.redirect('/auth/change-password');
        }
        
        const salt = bcrypt.genSaltSync(10);
        const passwordHash = bcrypt.hashSync(new_password, salt);
        await User.update(user.id, { password_hash: passwordHash });
        
        req.flash('success', '✅ Đổi mật khẩu thành công! Vui lòng đăng nhập lại.');
        req.session.destroy();
        res.redirect('/auth/login');
    } catch (error) {
        console.error(error);
        req.flash('error', 'Đã xảy ra lỗi');
        res.redirect('/auth/change-password');
    }
});

module.exports = router;