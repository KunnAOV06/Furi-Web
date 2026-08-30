const { getQuery, allQuery, runQuery } = require('../database');

class NewUserDiscount {
    static async findById(id) {
        return getQuery('SELECT * FROM new_user_discounts WHERE id = ?', [id]);
    }

    static async findByUser(userId) {
        return getQuery('SELECT * FROM new_user_discounts WHERE user_id = ?', [userId]);
    }

    static async findByCode(code) {
        return getQuery('SELECT * FROM new_user_discounts WHERE code = ? AND used = 0', [code]);
    }

    static async create(data) {
        const { user_id, code, discount_percent } = data;
        const result = await runQuery(
            `INSERT INTO new_user_discounts (user_id, code, discount_percent, used, created_at) 
             VALUES (?, ?, ?, 0, CURRENT_TIMESTAMP)`,
            [user_id, code, discount_percent || 15]
        );
        return this.findById(result.id);
    }

    static async markUsed(id) {
        await runQuery('UPDATE new_user_discounts SET used = 1 WHERE id = ?', [id]);
        return this.findById(id);
    }

    static async getAll() {
        return allQuery('SELECT * FROM new_user_discounts ORDER BY created_at DESC');
    }
}

module.exports = NewUserDiscount;