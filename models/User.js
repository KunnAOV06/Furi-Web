const { getQuery, allQuery, runQuery } = require('../database');
const bcrypt = require('bcryptjs');
const crypto = require('crypto');

class User {
    static async findById(id) {
        return getQuery('SELECT * FROM users WHERE id = ?', [id]);
    }
    
    static async findByUsername(username) {
        return getQuery('SELECT * FROM users WHERE username = ?', [username]);
    }
    
    static async findByEmail(email) {
        return getQuery('SELECT * FROM users WHERE email = ?', [email]);
    }
    
    static async findByReferralCode(code) {
        return getQuery('SELECT * FROM users WHERE referral_code = ?', [code]);
    }
    
    static async findByDepositCode(code) {
        return getQuery('SELECT * FROM users WHERE deposit_code = ?', [code]);
    }
    
    static async create(userData) {
        const { username, email, password, referral_code } = userData;
        const salt = bcrypt.genSaltSync(10);
        const passwordHash = bcrypt.hashSync(password, salt);
        const referralCode = referral_code || crypto.randomBytes(6).toString('base64url');
        const depositCode = `FURIWEB${Date.now().toString().slice(-6)}`;
        
        const result = await runQuery(
            `INSERT INTO users (username, email, password_hash, referral_code, deposit_code, created_at, is_admin, is_seller) 
             VALUES (?, ?, ?, ?, ?, datetime('now'), 0, 0)`,
            [username, email, passwordHash, referralCode, depositCode]
        );
        
        return this.findById(result.id);
    }
    
    static async update(id, data) {
        const fields = Object.keys(data).map(k => `${k} = ?`).join(', ');
        const values = Object.values(data);
        values.push(id);
        await runQuery(`UPDATE users SET ${fields} WHERE id = ?`, values);
        return this.findById(id);
    }
    
    static async getAll() {
        return allQuery('SELECT * FROM users ORDER BY id DESC');
    }
    
    static async getSellers() {
        return allQuery('SELECT * FROM users WHERE is_seller = 1 ORDER BY total_sales DESC');
    }
    
    static async getAdmins() {
        return allQuery('SELECT * FROM users WHERE is_admin = 1');
    }
    
    static async updateBalance(userId, amount) {
        await runQuery('UPDATE users SET balance = balance + ? WHERE id = ?', [amount, userId]);
        return this.findById(userId);
    }
}

module.exports = User;