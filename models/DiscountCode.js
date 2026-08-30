const { getQuery, allQuery, runQuery } = require('../database');

class DiscountCode {
    static async findById(id) {
        return getQuery('SELECT * FROM discount_codes WHERE id = ?', [id]);
    }
    
    static async findByCode(code) {
        return getQuery('SELECT * FROM discount_codes WHERE code = ?', [code.toUpperCase()]);
    }
    
    static async create(data) {
        const { code, discount_percent, valid_until, max_uses } = data;
        const result = await runQuery(
            `INSERT INTO discount_codes (code, discount_percent, valid_until, max_uses, used_count) 
             VALUES (?, ?, ?, ?, 0)`,
            [code.toUpperCase(), discount_percent, valid_until, max_uses]
        );
        return this.findById(result.id);
    }
    
    static async use(code) {
        const discount = await this.findByCode(code);
        if (!discount) return null;
        if (discount.used_count < discount.max_uses && new Date() < new Date(discount.valid_until)) {
            await runQuery('UPDATE discount_codes SET used_count = used_count + 1 WHERE id = ?', [discount.id]);
            return this.findById(discount.id);
        }
        return null;
    }
    
    static async getAll() {
        return allQuery('SELECT * FROM discount_codes ORDER BY valid_until DESC');
    }
    
    static async delete(id) {
        await runQuery('DELETE FROM discount_codes WHERE id = ?', [id]);
        return true;
    }
}

module.exports = DiscountCode;