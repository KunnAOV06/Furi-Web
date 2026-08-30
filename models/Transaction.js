const { getQuery, allQuery, runQuery } = require('../database');

class Transaction {
    static async findById(id) {
        return getQuery('SELECT * FROM transactions WHERE id = ?', [id]);
    }
    
    static async findByUser(userId) {
        return allQuery('SELECT * FROM transactions WHERE user_id = ? ORDER BY created_at DESC', [userId]);
    }
    
    static async create(data) {
        const { user_id, amount, type, description } = data;
        const result = await runQuery(
            `INSERT INTO transactions (user_id, amount, type, description, created_at) 
             VALUES (?, ?, ?, ?, datetime('now'))`,
            [user_id, amount, type, description]
        );
        return this.findById(result.id);
    }
    
    static async getAll() {
        return allQuery(
            `SELECT t.*, u.username 
             FROM transactions t 
             LEFT JOIN users u ON t.user_id = u.id 
             ORDER BY t.created_at DESC`
        );
    }
}

module.exports = Transaction;