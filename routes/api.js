const express = require('express');
const router = express.Router();
const { isAuthenticated } = require('../middleware/auth');
const FileItem = require('../models/FileItem');
const SiteSettings = require('../models/SiteSettings');

// Welcome banner
router.get('/welcome-banner', async (req, res) => {
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

// Search products
router.get('/search', async (req, res) => {
    try {
        const { q } = req.query;
        if (!q) {
            return res.json({ results: [] });
        }
        const results = await FileItem.search(q);
        res.json({ results });
    } catch (error) {
        res.status(500).json({ error: 'Lỗi tìm kiếm' });
    }
});

module.exports = router;