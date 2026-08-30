const express = require('express');
const router = express.Router();
const path = require('path');
const fs = require('fs');
const config = require('../config');
const upload = require('../middleware/upload');
const { isAuthenticated, isSeller } = require('../middleware/auth');
const FileItem = require('../models/FileItem');
const Purchase = require('../models/Purchase');

// Get thumbnail
router.get('/thumbnail/:filename', (req, res) => {
    const filepath = path.join(config.thumbnailFolder, req.params.filename);
    if (fs.existsSync(filepath)) {
        res.sendFile(path.resolve(filepath));
    } else {
        res.status(404).send('Không tìm thấy ảnh');
    }
});

// File detail
router.get('/:id', async (req, res) => {
    try {
        const file = await FileItem.findById(req.params.id);
        if (!file || !file.is_active) {
            req.flash('error', 'Sản phẩm không tồn tại');
            return res.redirect('/');
        }
        
        let isPurchased = false;
        let purchase = null;
        if (req.user) {
            purchase = await Purchase.checkPurchased(req.user.id, file.id);
            isPurchased = !!purchase;
        }
        
        res.render('file_detail', {
            title: file.product_name,
            file,
            isPurchased,
            purchase,
        });
    } catch (error) {
        console.error(error);
        res.redirect('/');
    }
});

// Get Free - Redirect to free link
router.get('/get-free/:id', isAuthenticated, async (req, res) => {
    try {
        const file = await FileItem.findById(req.params.id);
        if (!file || !file.free_link) {
            req.flash('error', 'Sản phẩm này không có link nhận Free');
            return res.redirect(`/file/${req.params.id}`);
        }
        
        await FileItem.incrementDownload(file.id);
        res.redirect(file.free_link);
    } catch (error) {
        console.error(error);
        req.flash('error', 'Đã xảy ra lỗi');
        res.redirect(`/file/${req.params.id}`);
    }
});

// Upload file
router.get('/upload', isAuthenticated, isSeller, (req, res) => {
    res.render('upload', { title: 'Đăng bán sản phẩm' });
});

router.post('/upload', isAuthenticated, isSeller, upload.fields([
    { name: 'thumbnail', maxCount: 1 },
    { name: 'file', maxCount: 1 },
    { name: 'demo_file', maxCount: 1 },
]), async (req, res) => {
    try {
        const { product_name, category, price, description, free_link, demo_type, demo_link, demo_description } = req.body;
        const thumbnail = req.files?.thumbnail?.[0] || null;
        const file = req.files?.file?.[0] || null;
        
        const fileItem = await FileItem.create({
            product_name: product_name || 'Sản phẩm mới',
            category: category || 'mod_nut',
            price: parseFloat(price) || 0,
            description: description || '',
            free_link: free_link || '',
            uploaded_by: req.user.id,
            filename: file ? file.filename : null,
            original_name: file ? file.originalname : 'Không có file',
            file_type: file ? path.extname(file.originalname).substring(1).toUpperCase() : 'other',
            file_size: file ? file.size : 0,
            thumbnail: thumbnail ? thumbnail.filename : null,
        });
        
        if (free_link) {
            req.flash('success', '✅ Đăng sản phẩm thành công! Người dùng có thể NHẬN FREE qua link.');
        } else if (file) {
            req.flash('success', '✅ Đăng sản phẩm thành công!');
        }
        res.redirect('/file/my-files');
    } catch (error) {
        console.error(error);
        req.flash('error', 'Đăng sản phẩm thất bại');
        res.redirect('/file/upload');
    }
});

// My files
router.get('/my-files', isAuthenticated, isSeller, async (req, res) => {
    try {
        const files = await FileItem.findBySeller(req.user.id);
        res.render('my_files', { title: 'Sản phẩm của tôi', files });
    } catch (error) {
        console.error(error);
        res.redirect('/');
    }
});

// Download file (purchased)
router.get('/download/:id', isAuthenticated, async (req, res) => {
    try {
        const file = await FileItem.findById(req.params.id);
        if (!file) {
            req.flash('error', 'File không tồn tại');
            return res.redirect('/');
        }
        
        const purchase = await Purchase.checkPurchased(req.user.id, file.id);
        if (!purchase) {
            req.flash('error', 'Bạn chưa mua sản phẩm này');
            return res.redirect(`/file/${req.params.id}`);
        }
        
        const filepath = path.join(config.uploadFolder, file.filename);
        if (!fs.existsSync(filepath)) {
            req.flash('error', 'File không tồn tại hoặc đã bị xóa');
            return res.redirect(`/file/${req.params.id}`);
        }
        
        await FileItem.incrementDownload(file.id);
        res.download(filepath, file.original_name);
    } catch (error) {
        console.error(error);
        req.flash('error', 'Đã xảy ra lỗi');
        res.redirect('/');
    }
});

// Delete file
router.post('/delete/:id', isAuthenticated, async (req, res) => {
    try {
        const file = await FileItem.findById(req.params.id);
        if (!file) {
            req.flash('error', 'File không tồn tại');
            return res.redirect('/file/my-files');
        }
        
        if (!req.user.is_admin && file.uploaded_by !== req.user.id) {
            req.flash('error', 'Bạn không có quyền xóa file này');
            return res.redirect('/file/my-files');
        }
        
        // Xóa file vật lý
        const filepath = path.join(config.uploadFolder, file.filename);
        if (fs.existsSync(filepath)) fs.unlinkSync(filepath);
        const thumbpath = path.join(config.thumbnailFolder, file.thumbnail);
        if (fs.existsSync(thumbpath)) fs.unlinkSync(thumbpath);
        
        await FileItem.delete(file.id);
        req.flash('success', 'Đã xóa sản phẩm thành công');
        res.redirect('/file/my-files');
    } catch (error) {
        console.error(error);
        req.flash('error', 'Xóa thất bại');
        res.redirect('/file/my-files');
    }
});

// Toggle file status
router.post('/toggle/:id', isAuthenticated, async (req, res) => {
    try {
        if (!req.user.is_admin) {
            req.flash('error', 'Bạn không có quyền');
            return res.redirect('/file/my-files');
        }
        await FileItem.toggleActive(req.params.id);
        req.flash('success', 'Đã cập nhật trạng thái');
        res.redirect('/file/my-files');
    } catch (error) {
        console.error(error);
        req.flash('error', 'Cập nhật thất bại');
        res.redirect('/file/my-files');
    }
});

module.exports = router;