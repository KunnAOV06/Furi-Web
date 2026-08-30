const sqlite3 = require('sqlite3').verbose();
const path = require('path');
const bcrypt = require('bcryptjs');

const dbPath = path.resolve(__dirname, '../datafuri.db');
const db = new sqlite3.Database(dbPath);

const runQuery = (sql) => {
    return new Promise((resolve, reject) => {
        db.run(sql, (err) => {
            if (err) reject(err);
            else resolve();
        });
    });
};

const createTables = async () => {
    try {
        // Users
        await runQuery(`
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                balance REAL DEFAULT 0,
                is_admin INTEGER DEFAULT 0,
                is_seller INTEGER DEFAULT 0,
                referral_code TEXT UNIQUE,
                referred_by INTEGER,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                reset_token TEXT,
                reset_token_expiry DATETIME,
                deposit_code TEXT UNIQUE,
                bank_name TEXT,
                bank_account_name TEXT,
                bank_account_number TEXT,
                total_sales REAL DEFAULT 0,
                total_withdrawn REAL DEFAULT 0,
                withdraw_count INTEGER DEFAULT 0,
                FOREIGN KEY (referred_by) REFERENCES users(id)
            )
        `);

        // File Items
        await runQuery(`
            CREATE TABLE IF NOT EXISTS file_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_name TEXT NOT NULL,
                filename TEXT,
                original_name TEXT,
                price REAL DEFAULT 0,
                description TEXT,
                uploaded_by INTEGER,
                download_count INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                is_active INTEGER DEFAULT 1,
                file_type TEXT DEFAULT 'other',
                file_size INTEGER DEFAULT 0,
                thumbnail TEXT,
                category TEXT DEFAULT 'mod_nut',
                free_link TEXT,
                has_demo INTEGER DEFAULT 0,
                demo_type TEXT DEFAULT 'none',
                demo_file TEXT,
                demo_link TEXT,
                demo_description TEXT,
                FOREIGN KEY (uploaded_by) REFERENCES users(id)
            )
        `);

        // Purchases
        await runQuery(`
            CREATE TABLE IF NOT EXISTS purchases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                file_id INTEGER NOT NULL,
                amount_paid REAL NOT NULL,
                seller_earned REAL DEFAULT 0,
                admin_earned REAL DEFAULT 0,
                discount_applied REAL DEFAULT 0,
                purchased_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                download_token TEXT UNIQUE,
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (file_id) REFERENCES file_items(id)
            )
        `);

        // Deposit Requests
        await runQuery(`
            CREATE TABLE IF NOT EXISTS deposit_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                transaction_code TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                note TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                completed_at DATETIME,
                expires_at DATETIME,
                confirmed_at DATETIME,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        `);

        // Withdraw Requests
        await runQuery(`
            CREATE TABLE IF NOT EXISTS withdraw_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                fee REAL DEFAULT 0,
                net_amount REAL DEFAULT 0,
                bank_name TEXT NOT NULL,
                bank_account_name TEXT NOT NULL,
                bank_account_number TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                note TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                processed_at DATETIME,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        `);

        // Discount Codes
        await runQuery(`
            CREATE TABLE IF NOT EXISTS discount_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE NOT NULL,
                discount_percent REAL NOT NULL,
                valid_until DATETIME NOT NULL,
                max_uses INTEGER DEFAULT 1,
                used_count INTEGER DEFAULT 0
            )
        `);

        // Transactions
        await runQuery(`
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                type TEXT NOT NULL,
                description TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        `);

        // Site Settings
        await runQuery(`
            CREATE TABLE IF NOT EXISTS site_settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT UNIQUE NOT NULL,
                value TEXT,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        `);

        // New User Discounts
        await runQuery(`
            CREATE TABLE IF NOT EXISTS new_user_discounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER UNIQUE NOT NULL,
                code TEXT UNIQUE NOT NULL,
                discount_percent REAL DEFAULT 15,
                used INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        `);

        // Global Sales
        await runQuery(`
            CREATE TABLE IF NOT EXISTS global_sales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                is_active INTEGER DEFAULT 0,
                discount_percent REAL DEFAULT 0,
                start_date DATETIME,
                end_date DATETIME,
                updated_by INTEGER,
                FOREIGN KEY (updated_by) REFERENCES users(id)
            )
        `);

        // Product Sales
        await runQuery(`
            CREATE TABLE IF NOT EXISTS product_sales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id INTEGER UNIQUE NOT NULL,
                discount_percent REAL DEFAULT 0,
                is_active INTEGER DEFAULT 0,
                start_date DATETIME,
                end_date DATETIME,
                FOREIGN KEY (file_id) REFERENCES file_items(id)
            )
        `);

        // Referral IPs
        await runQuery(`
            CREATE TABLE IF NOT EXISTS referral_ips (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ip_address TEXT NOT NULL,
                referred_user_id INTEGER,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (referred_user_id) REFERENCES users(id)
            )
        `);

        // OTP Verifications
        await runQuery(`
            CREATE TABLE IF NOT EXISTS otp_verifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL,
                otp_code TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                expires_at DATETIME NOT NULL,
                is_used INTEGER DEFAULT 0
            )
        `);

        console.log('✅ Tạo bảng thành công!');

        // Tạo admin
        const admin = await new Promise((resolve) => {
            db.get('SELECT * FROM users WHERE username = ?', ['Furiadmin'], (err, row) => {
                resolve(row);
            });
        });

        if (!admin) {
            const salt = bcrypt.genSaltSync(10);
            const passwordHash = bcrypt.hashSync('AdminFuri2006@', salt);
            const referralCode = require('crypto').randomBytes(6).toString('base64url');
            const depositCode = 'FURIWEB000001';

            await runQuery(`
                INSERT INTO users (username, email, password_hash, is_admin, is_seller, referral_code, deposit_code, created_at)
                VALUES (?, ?, ?, 1, 1, ?, ?, CURRENT_TIMESTAMP)
            `, ['Furiadmin', 'adminfuriweb@gmail.com', passwordHash, referralCode, depositCode]);

            console.log('✅ Admin created: Furiadmin / AdminFuri2006@');
        }

        console.log('🎉 Database initialized successfully!');
        db.close();
    } catch (error) {
        console.error('❌ Lỗi:', error);
        db.close();
    }
};

createTables();