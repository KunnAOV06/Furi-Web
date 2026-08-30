const { getQuery, allQuery, runQuery } = require('../database');
const crypto = require('crypto');

class Purchase {
    static async findById(id) {
        return getQuery('SELECT * FROM purchases WHERE id = ?', [id]);
    }
    
    static async findByUser(userId) {
        return allQuery(
            `SELECT p.*, f.product_name, f.thumbnail, f.original_name 
             FROM purchases p 
             LEFT JOIN file_items f ON p.file_id = f.id 
             WHERE p.user_id = ? 
             ORDER BY p.purchased_at DESC`,
            [userId]
        );
    }
    
    static async findByFile(fileId) {
        return allQuery('SELECT * FROM purchases WHERE file_id = ?', [fileId]);
    }
    
    static async findByToken(token) {
        return getQuery('SELECT * FROM purchases WHERE download_token = ?', [token]);
    }
    
    static async create(data) {
        const { user_id, file_id, amount_paid, seller_earned, admin_earned, discount_applied } = data;
        const downloadToken = crypto.randomBytes(32).toString('hex');
        const result = await runQuery(
            `INSERT INTO purchases (user_id, file_id, amount_paid, seller_earned, admin_earned, discount_applied, download_token, purchased_at) 
             VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))`,
            [user_id, file_id, amount_paid, seller_earned, admin_earned, discount_applied, downloadToken]
        );
        return this.findById(result.id);
    }
    
    static async checkPurchased(userId, fileId) {
        return getQuery('SELECT * FROM purchases WHERE user_id = ? AND file_id = ?', [userId, fileId]);
    }
    
    static async getTotalSpent(userId) {
        const result = await getQuery('SELECT SUM(amount_paid) as total FROM purchases WHERE user_id = ?', [userId]);
        return result?.total || 0;
    }
    
    static async getAll() {
        return allQuery(
            `SELECT p.*, u.username, f.product_name 
             FROM purchases p 
             LEFT JOIN users u ON p.user_id = u.id 
             LEFT JOIN file_items f ON p.file_id = f.id 
             ORDER BY p.purchased_at DESC`
        );
    }
    
    static async getRecent(limit) {
        return allQuery(
            `SELECT p.*, u.username, f.product_name 
             FROM purchases p 
             LEFT JOIN users u ON p.user_id = u.id 
             LEFT JOIN file_items f ON p.file_id = f.id 
             ORDER BY p.purchased_at DESC LIMIT ?`,
            [limit]
        );
    }
}

module.exports = Purchase;