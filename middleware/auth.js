const jwt = require('jsonwebtoken');
const config = require('../config');
const User = require('../models/User');

// Middleware kiểm tra đăng nhập
const isAuthenticated = async (req, res, next) => {
    if (req.session && req.session.userId) {
        const user = await User.findById(req.session.userId);
        if (user) {
            req.user = user;
            return next();
        }
    }
    res.redirect('/login');
};

// Middleware kiểm tra Admin
const isAdmin = async (req, res, next) => {
    if (!req.user) {
        req.flash('error', 'Vui lòng đăng nhập');
        return res.redirect('/login');
    }
    if (!req.user.is_admin) {
        req.flash('error', 'Bạn không có quyền truy cập');
        return res.redirect('/');
    }
    next();
};

// Middleware kiểm tra Seller
const isSeller = async (req, res, next) => {
    if (!req.user) {
        req.flash('error', 'Vui lòng đăng nhập');
        return res.redirect('/login');
    }
    if (!req.user.is_seller && !req.user.is_admin) {
        req.flash('error', 'Bạn cần được cấp quyền bán hàng');
        return res.redirect('/');
    }
    next();
};

// Middleware để lấy user cho tất cả routes
const loadUser = async (req, res, next) => {
    if (req.session && req.session.userId) {
        const user = await User.findById(req.session.userId);
        if (user) {
            req.user = user;
            res.locals.user = user;
        }
    }
    next();
};

module.exports = {
    isAuthenticated,
    isAdmin,
    isSeller,
    loadUser,
};