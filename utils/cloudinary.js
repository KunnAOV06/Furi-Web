const cloudinary = require('cloudinary').v2;
const config = require('../config');

// Cấu hình Cloudinary
cloudinary.config({
    cloud_name: config.cloudinary.cloudName,
    api_key: config.cloudinary.apiKey,
    api_secret: config.cloudinary.apiSecret,
});

// Upload file lên Cloudinary
const uploadToCloudinary = async (filePath, options = {}) => {
    try {
        const result = await cloudinary.uploader.upload(filePath, {
            folder: options.folder || 'furi_web',
            resource_type: options.resource_type || 'auto',
            quality: options.quality || 'auto',
            fetch_format: options.format || 'auto',
            ...options
        });

        return {
            success: true,
            url: result.secure_url,
            public_id: result.public_id,
            format: result.format,
            size: result.bytes,
            width: result.width,
            height: result.height,
        };
    } catch (error) {
        console.error('❌ Lỗi upload Cloudinary:', error);
        return { success: false, error: error.message };
    }
};

// Xóa file trên Cloudinary
const deleteFromCloudinary = async (publicId) => {
    try {
        const result = await cloudinary.uploader.destroy(publicId);
        return { success: true, result };
    } catch (error) {
        console.error('❌ Lỗi xóa Cloudinary:', error);
        return { success: false, error: error.message };
    }
};

// Tạo URL ảnh với transformation
const getOptimizedUrl = (publicId, options = {}) => {
    return cloudinary.url(publicId, {
        width: options.width || 500,
        height: options.height || 500,
        crop: options.crop || 'fill',
        quality: options.quality || 'auto',
        fetch_format: options.format || 'auto',
        ...options
    });
};

// Upload ảnh từ URL
const uploadFromUrl = async (url, options = {}) => {
    try {
        const result = await cloudinary.uploader.upload(url, {
            folder: options.folder || 'furi_web',
            ...options
        });
        return {
            success: true,
            url: result.secure_url,
            public_id: result.public_id,
        };
    } catch (error) {
        console.error('❌ Lỗi upload từ URL:', error);
        return { success: false, error: error.message };
    }
};

module.exports = {
    cloudinary,
    uploadToCloudinary,
    deleteFromCloudinary,
    getOptimizedUrl,
    uploadFromUrl,
};