// middleware/upload.js
const multer = require('multer');
const path = require('path');
const fs = require('fs');
const config = require('../config');

// Tạo thư mục nếu chưa có
const createDir = (dir) => {
    if (!fs.existsSync(dir)) {
        fs.mkdirSync(dir, { recursive: true });
    }
};

createDir(config.uploadFolder);
createDir(config.demoFolder);
createDir(config.thumbnailFolder);

// Cấu hình storage
const storage = multer.diskStorage({
    destination: (req, file, cb) => {
        let folder = config.uploadFolder;
        if (file.fieldname === 'thumbnail') {
            folder = config.thumbnailFolder;
        } else if (file.fieldname === 'demo_file') {
            folder = config.demoFolder;
        }
        cb(null, folder);
    },
    filename: (req, file, cb) => {
        const timestamp = Date.now();
        const ext = path.extname(file.originalname);
        const name = path.basename(file.originalname, ext);
        cb(null, `${timestamp}_${name}${ext}`);
    }
});

// Filter file
const fileFilter = (req, file, cb) => {
    const allowedExtensions = config.allowedExtensions;
    const ext = path.extname(file.originalname).toLowerCase().substring(1);
    if (allowedExtensions.includes(ext) || file.fieldname === 'file' || file.fieldname === 'demo_file') {
        cb(null, true);
    } else {
        cb(new Error('Định dạng file không được hỗ trợ'), false);
    }
};

// Multer instance
const upload = multer({
    storage: storage,
    limits: {
        fileSize: config.maxFileSize,
    },
    fileFilter: fileFilter,
});

module.exports = upload;
