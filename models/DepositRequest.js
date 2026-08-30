const { getQuery, allQuery, runQuery } = require('../database');

class DepositRequest {
    static async findById(id) {
        return getQuery('SELECT * FROM deposit_requests WHERE id = ?', [id]);
    }
    
    static async findByUser(userId) {
        return allQuery('SELECT * FROM deposit_requests WHERE user_id = ? ORDER BY created_at DESC', [userId]);
    }
    
    static async findByCode(transactionCode) {
        return getQuery('SELECT * FROM deposit_requests WHERE transaction_code = ?', [transactionCode]);
    }
    
    static async create(data) {
        const { user_id, amount, transaction_code } = data;
        const result = await runQuery(
            `INSERT INTO deposit_requests (user_id, amount, transaction_code, status, created_at) 
             VALUES (?, ?, ?, 'pending', datetime('now'))`,
            [user_id, amount, transaction_code]
        );
        return this.findById(result.id);
    }
    
    static async updateStatus(id, status, note = null) {
        const query = note ? 
            `UPDATE deposit_requests SET status = ?, note = ?, completed_at = datetime('now') WHERE id = ?` :
            `UPDATE deposit_requests SET status = ?, completed_at = datetime('now') WHERE id = ?`;
        const params = note ? [status, note, id] : [status, id];
        await runQuery(query, params);
        return this.findById(id);
    }
    
    static async getAllPending() {
        return allQuery('SELECT * FROM deposit_requests WHERE status IN ("pending", "confirmed") ORDER BY created_at ASC');
    }
    
    static async getAll() {
        return allQuery(
            `SELECT d.*, u.username, u.email 
             FROM deposit_requests d 
             LEFT JOIN users u ON d.user_id = u.id 
             ORDER BY d.created_at DESC`
        );
    }
}

module.exports = DepositRequest;