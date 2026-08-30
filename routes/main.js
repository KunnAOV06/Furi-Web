const express = require('express');
const router = express.Router();
const FileItem = require('../models/FileItem');
const SiteSettings = require('../models/SiteSettings');

// Trang chủ
router.get('/', async (req, res) => {
    try {
        const files = await FileItem.getActiveLimit(12);
        const hotFiles = await FileItem.getHot(5);
        res.render('index', { 
            title: 'FURI WEB - Premium Mod Store',
            files,
            hotFiles,
        });
    } catch (error) {
        console.error(error);
        res.render('index', { 
            title: 'FURI WEB - Premium Mod Store',
            files: [],
            hotFiles: [],
        });
    }
});

// Danh mục MOD NÚT
router.get('/mod-nut', async (req, res) => {
    try {
        const files = await FileItem.getByCategory('mod_nut');
        res.render('category', {
            files,
            category: 'mod_nut',
            category_name: 'MOD NÚT',
            category_icon: 'fa-gamepad',
            category_color: 'var(--neon-red)',
            category_description: 'Mod FX, Joystick, Icon Shop trực tiếp',
        });
    } catch (error) {
        res.redirect('/');
    }
});

// Danh mục MOD TRANG PHỤC
router.get('/mod-trang-phuc', async (req, res) => {
    try {
        const files = await FileItem.getByCategory('mod_trang_phuc');
        res.render('category', {
            files,
            category: 'mod_trang_phuc',
            category_name: 'MOD TRANG PHỤC',
            category_icon: 'fa-tshirt',
            category_color: 'var(--neon-blue)',
            category_description: 'Kho Skin Mod đa dạng tải từ Server',
        });
    } catch (error) {
        res.redirect('/');
    }
});

// Danh mục TOOL AOV
router.get('/tool-aov', async (req, res) => {
    try {
        const files = await FileItem.getByCategory('tool_aov');
        res.render('category', {
            files,
            category: 'tool_aov',
            category_name: 'TOOL AOV',
            category_icon: 'fa-tools',
            category_color: 'var(--neon-green)',
            category_description: 'Công cụ hỗ trợ AOV tối ưu',
        });
    } catch (error) {
        res.redirect('/');
    }
});

// Danh mục MOD THÔNG BÁO
router.get('/mod-thong-bao', async (req, res) => {
    try {
        const files = await FileItem.getByCategory('mod_thong_bao');
        res.render('category', {
            files,
            category: 'mod_thong_bao',
            category_name: 'MOD THÔNG BÁO',
            category_icon: 'fa-bell',
            category_color: 'var(--neon-cyan)',
            category_description: 'Thay đổi hiệu ứng thông báo hạ gục',
        });
    } catch (error) {
        res.redirect('/');
    }
});

// API Welcome Banner
router.get('/api/welcome-banner', async (req, res) => {
    try {
        const setting = await SiteSettings.getByKey('welcome_banner');
        if (setting) {
            res.json({ content: setting.value, active: true });
        } else {
            res.json({ 
                content: '🎉 Chào mừng bạn đến với FURI WEB! Mua sắm an toàn, chất lượng cao!', 
                active: true 
            });
        }
    } catch (error) {
        res.json({ 
            content: '🎉 Chào mừng bạn đến với FURI WEB! Mua sắm an toàn, chất lượng cao!', 
            active: true 
        });
    }
});

module.exports = router;