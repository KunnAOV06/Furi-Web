const express = require('express');
const session = require('express-session');
const path = require('path');
const cors = require('cors');
const morgan = require('morgan');
const helmet = require('helmet');
const rateLimit = require('express-rate-limit');
const dotenv = require('dotenv');
const flash = require('connect-flash');

dotenv.config();

const config = require('./config');
const { loadUser } = require('./middleware/auth');
const { formatPrice, formatDate } = require('./utils/helpers');

// Import routes
const authRoutes = require('./routes/auth');
const mainRoutes = require('./routes/main');
const fileRoutes = require('./routes/file');
const purchaseRoutes = require('./routes/purchase');
const depositRoutes = require('./routes/deposit');
const withdrawRoutes = require('./routes/withdraw');
const adminRoutes = require('./routes/admin');
const apiRoutes = require('./routes/api');

// Khởi tạo app
const app = express();

// Rate limiting
const limiter = rateLimit({
    windowMs: 15 * 60 * 1000,
    max: 100,
    message: 'Quá nhiều yêu cầu, vui lòng thử lại sau',
});

// Middleware
app.use(helmet({
    contentSecurityPolicy: false,
}));
app.use(cors());
app.use(morgan('dev'));
app.use(express.json());
app.use(express.urlencoded({ extended: true }));
app.use(express.static(path.join(__dirname, 'public')));
app.use('/uploads', express.static(path.join(__dirname, 'uploads')));

// Session
app.use(session({
    secret: config.secretKey,
    resave: false,
    saveUninitialized: false,
    cookie: {
        secure: config.nodeEnv === 'production',
        maxAge: 7 * 24 * 60 * 60 * 1000,
    },
}));

// Flash messages
app.use(flash());

// Load user middleware
app.use(loadUser);

// View engine
app.set('view engine', 'ejs');
app.set('views', path.join(__dirname, 'views'));

// Global locals
app.use((req, res, next) => {
    res.locals.formatPrice = formatPrice;
    res.locals.formatDate = formatDate;
    res.locals.user = req.user || null;
    res.locals.messages = req.flash();
    res.locals.currentPath = req.path;
    next();
});

// Routes
app.use('/', mainRoutes);
app.use('/auth', authRoutes);
app.use('/file', fileRoutes);
app.use('/purchase', purchaseRoutes);
app.use('/deposit', depositRoutes);
app.use('/withdraw', withdrawRoutes);
app.use('/admin', adminRoutes);
app.use('/api', apiRoutes);

// Error handling
app.use((req, res) => {
    res.status(404).render('404', { title: 'Không tìm thấy trang' });
});

app.use((err, req, res, next) => {
    console.error(err.stack);
    res.status(500).render('500', {
        title: 'Lỗi server',
        error: config.nodeEnv === 'development' ? err.message : 'Đã xảy ra lỗi, vui lòng thử lại sau',
    });
});

// ===== SỬA: Export cho Vercel =====
module.exports = app;

// ===== SỬA: Chạy local =====
if (require.main === module) {
    const PORT = config.port || 5000;
    app.listen(PORT, () => {
        console.log(`🚀 FURI WEB Server running on http://localhost:${PORT}`);
        console.log(`📦 Environment: ${config.nodeEnv}`);
    });
}
