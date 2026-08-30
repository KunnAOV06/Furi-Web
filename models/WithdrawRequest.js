const { getQuery, allQuery, runQuery } = require('../database');

class WithdrawRequest {
    static async findById(id) {
        return getQuery('SELECT * FROM withdraw_requests WHERE id = ?', [id]);
    }
    
    static async findByUser(userId) {
        return allQuery('SELECT * FROM withdraw_requests WHERE user_id = ? ORDER BY created_at DESC', [userId]);
    }
    
    static async create(data) {
        const { user_id, amount, fee, net_amount, bank_name, bank_account_name, bank_account_number } = data;
        const result = await runQuery(
            `INSERT INTO withdraw_requests 
             (user_id, amount, fee, net_amount, bank_name, bank_account_name, bank_account_number, status, created_at) 
             VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', datetime('now'))`,
            [user_id, amount, fee, net_amount, bank_name, bank_account_name, bank_account_number]
        );
        return this.findById(result.id);
    }
    
    static async updateStatus(id, status) {
        await runQuery('UPDATE withdraw_requests SET status = ?, processed_at = datetime("now") WHERE id = ?', [status, id]);
        return this.findById(id);
    }
    
    static async getAllPending() {
        return allQuery('SELECT * FROM withdraw_requests WHERE status = "pending" ORDER BY created_at ASC');
    }
    
    static async getAll() {
        return allQuery(
            `SELECT w.*, u.username, u.email 
             FROM withdraw_requests w 
             LEFT JOIN users u ON w.user_id = u.id 
             ORDER BY w.created_at DESC`
        );
    }
}

module.exports = WithdrawRequest;